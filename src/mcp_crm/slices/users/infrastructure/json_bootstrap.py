from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from mcp_crm.slices.users.application.ports import EmbeddingPort
from mcp_crm.slices.users.domain.errors import ConfigurationError
from mcp_crm.slices.users.infrastructure.config import Settings
from mcp_crm.slices.users.infrastructure.logging import get_logger

logger = get_logger(__name__)

_SUPPORTED_SUFFIXES = {".json", ".jsonl", ".ndjson"}
_COLLECTION_KEYS = ("users", "items", "records", "results", "data")
_NAME_CANDIDATES = (
    "name",
    "nome",
    "title",
    "titulo",
    "label",
    "code",
    "codigo",
    "ncm",
    "id",
    "key",
)
_EMAIL_CANDIDATES = ("email", "e_mail", "mail")
_DESCRIPTION_CANDIDATES = (
    "description",
    "descricao",
    "desc",
    "text",
    "texto",
    "summary",
    "resumo",
    "label",
)
_CODE_CANDIDATES = ("code", "codigo", "ncm", "id", "key")
_EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.IGNORECASE)
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_IMPORT_STATE_VERSION = 1


@dataclass(slots=True, frozen=True)
class _ImportState:
    version: int
    source_path: str
    source_size: int
    source_mtime_ns: int
    embedding_cache_key: str
    db_path: str
    parquet_path: str
    row_count: int


@dataclass(slots=True, frozen=True)
class _SourceFingerprint:
    path: Path
    size: int
    mtime_ns: int

    @property
    def token(self) -> str:
        return f"{self.size:x}-{self.mtime_ns:x}"


def bootstrap_json_import(settings: Settings, embedder: EmbeddingPort) -> None:
    if not settings.json_import_enabled:
        return

    source_path = _resolve_source_path(settings)
    if source_path is None:
        return

    settings.json_import_dir.mkdir(parents=True, exist_ok=True)
    settings.json_import_cache_dir.mkdir(parents=True, exist_ok=True)

    fingerprint = _fingerprint_source(source_path)
    embedding_cache_key = _embedding_cache_key(settings)
    parquet_path = settings.json_import_cache_dir / (
        f"{source_path.stem}-{embedding_cache_key}-{fingerprint.token}.parquet"
    )
    state_path = settings.json_import_cache_dir / "import-state.json"
    state = _load_state(state_path)
    if _is_current_state(
        state,
        fingerprint,
        embedding_cache_key,
        settings.db_path,
        parquet_path,
    ):
        return

    if parquet_path.exists():
        row_count = _count_parquet_rows(parquet_path)
    else:
        row_count = _build_parquet_cache(
            source_path,
            parquet_path,
            embedder,
            batch_size=settings.json_import_batch_size,
        )

    _rebuild_sqlite_from_parquet(
        parquet_path,
        settings.db_path,
        batch_size=settings.json_import_batch_size,
    )
    _cleanup_stale_parquet_files(
        settings.json_import_cache_dir,
        source_path.stem,
        embedding_cache_key,
        parquet_path,
    )
    _write_state(
        state_path,
        _ImportState(
            version=_IMPORT_STATE_VERSION,
            source_path=str(source_path),
            source_size=fingerprint.size,
            source_mtime_ns=fingerprint.mtime_ns,
            embedding_cache_key=embedding_cache_key,
            db_path=str(settings.db_path),
            parquet_path=str(parquet_path),
            row_count=row_count,
        ),
    )
    logger.warning(
        "runtime json import refreshed sqlite",
        extra={
            "event": "import.bootstrap",
            "source_path": str(source_path),
            "parquet_path": str(parquet_path),
            "db_path": str(settings.db_path),
            "row_count": row_count,
        },
    )


def _resolve_source_path(settings: Settings) -> Path | None:
    if settings.json_import_source_path is not None:
        source_path = settings.json_import_source_path
        if not source_path.exists():
            raise ConfigurationError(f"json import source was not found: {source_path}")
        return source_path

    import_candidates = _discover_source_candidates(settings.json_import_dir)
    if import_candidates:
        return import_candidates[0]
    return None


def _discover_source_candidates(directory: Path) -> list[Path]:
    if not directory.exists() or not directory.is_dir():
        return []

    try:
        candidates = [
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in _SUPPORTED_SUFFIXES
        ]
    except OSError:
        return []

    candidates.sort(key=_source_candidate_sort_key, reverse=True)
    return candidates


def _source_candidate_sort_key(path: Path) -> tuple[int, str]:
    return (path.stat().st_mtime_ns, path.name.lower())


def _fingerprint_source(source_path: Path) -> _SourceFingerprint:
    stat = source_path.stat()
    return _SourceFingerprint(
        path=source_path,
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
    )


def _load_state(state_path: Path) -> _ImportState | None:
    if not state_path.exists():
        return None
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
        return _ImportState(**raw)
    except (OSError, TypeError, ValueError):
        return None


def _is_current_state(
    state: _ImportState | None,
    fingerprint: _SourceFingerprint,
    embedding_cache_key: str,
    db_path: Path,
    parquet_path: Path,
) -> bool:
    if state is None or not db_path.exists() or not parquet_path.exists():
        return False
    return (
        state.version == _IMPORT_STATE_VERSION
        and state.source_path == str(fingerprint.path)
        and state.source_size == fingerprint.size
        and state.source_mtime_ns == fingerprint.mtime_ns
        and state.embedding_cache_key == embedding_cache_key
        and state.db_path == str(db_path)
        and state.parquet_path == str(parquet_path)
    )


def _embedding_cache_key(settings: Settings) -> str:
    raw = f"{settings.embedding_provider}-{settings.embedding_model}".lower()
    return _SLUG_RE.sub("-", raw).strip("-") or "default"


def _write_state(state_path: Path, state: _ImportState) -> None:
    state_path.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")


def _build_parquet_cache(
    source_path: Path,
    parquet_path: Path,
    embedder: EmbeddingPort,
    *,
    batch_size: int,
) -> int:
    pl = _require_polars()
    normalized_rows = _normalize_records(source_path)
    descriptions = [row["description"] for row in normalized_rows]
    embeddings = embedder.embed_many(descriptions, batch_size=batch_size)
    frame = pl.DataFrame(normalized_rows)
    frame = frame.with_columns(pl.Series("embedding", embeddings))
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(parquet_path)
    return int(frame.height)


def _normalize_records(source_path: Path) -> list[dict[str, str]]:
    pl = _require_polars()
    records = _load_json_records(source_path)
    flattened = [
        _flatten_record(record) for record in records if isinstance(record, dict)
    ]
    if not flattened:
        raise ConfigurationError(
            f"json import source had no object rows: {source_path}"
        )

    frame = pl.DataFrame(flattened, strict=False).with_row_index("source_row")
    columns = frame.columns
    name_columns = _match_columns(columns, _NAME_CANDIDATES)
    email_columns = _match_columns(columns, _EMAIL_CANDIDATES)
    code_columns = _match_columns(columns, _CODE_CANDIDATES)
    description_columns = _match_columns(columns, _DESCRIPTION_CANDIDATES)

    seen_emails: set[str] = set()
    normalized_rows: list[dict[str, str]] = []
    for row in frame.iter_rows(named=True):
        source_row = int(row["source_row"])
        name = _resolve_name(row, name_columns, code_columns, source_row)
        description = _resolve_description(
            row,
            name=name,
            name_columns=name_columns,
            email_columns=email_columns,
            code_columns=code_columns,
            description_columns=description_columns,
        )
        email = _resolve_email(row, email_columns, name, source_row, seen_emails)
        normalized_rows.append(
            {
                "name": name,
                "email": email,
                "description": description,
            }
        )

    return normalized_rows


def _load_json_records(source_path: Path) -> list[dict[str, Any]]:
    suffix = source_path.suffix.lower()
    if suffix not in _SUPPORTED_SUFFIXES:
        raise ConfigurationError(f"unsupported json import file: {source_path}")

    if suffix in {".jsonl", ".ndjson"}:
        rows = []
        for line in source_path.read_text(encoding="utf-8").splitlines():
            candidate = line.strip()
            if not candidate:
                continue
            rows.append(json.loads(candidate))
        return rows

    raw = json.loads(source_path.read_text(encoding="utf-8"))
    collection = _find_collection(raw)
    if collection is None:
        raise ConfigurationError(
            f"json import source had no supported record collection: {source_path}"
        )
    return collection


def _find_collection(value: Any) -> list[dict[str, Any]] | None:
    if isinstance(value, list):
        if all(isinstance(item, dict) for item in value):
            return value
        return None
    if isinstance(value, dict):
        for key in _COLLECTION_KEYS:
            if key in value:
                found = _find_collection(value[key])
                if found is not None:
                    return found
        for candidate in value.values():
            found = _find_collection(candidate)
            if found is not None:
                return found
        return [value]
    return None


def _flatten_record(record: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in record.items():
        field_name = f"{prefix}_{key}" if prefix else str(key)
        if isinstance(value, dict):
            flattened.update(_flatten_record(value, field_name))
            continue
        flattened[field_name] = value
    return flattened


def _match_column(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    lowered = {column.lower(): column for column in columns}
    for candidate in candidates:
        if candidate in lowered:
            return lowered[candidate]
    for candidate in candidates:
        suffix = f"_{candidate}"
        for column in columns:
            if column.lower().endswith(suffix):
                return column
    return None


def _match_columns(columns: list[str], candidates: tuple[str, ...]) -> list[str]:
    matched: list[str] = []
    for candidate in candidates:
        column = _match_column(columns, (candidate,))
        if column is not None and column not in matched:
            matched.append(column)
    return matched


def _resolve_name(
    row: dict[str, Any],
    name_columns: list[str],
    code_columns: list[str],
    source_row: int,
) -> str:
    for column in [*name_columns, *code_columns]:
        value = _stringify_value(row.get(column))
        if value:
            return value
    return f"imported-record-{source_row + 1}"


def _resolve_description(
    row: dict[str, Any],
    *,
    name: str,
    name_columns: list[str],
    email_columns: list[str],
    code_columns: list[str],
    description_columns: list[str],
) -> str:
    parts: list[str] = []
    if description_columns:
        for column in description_columns:
            value = _stringify_value(row.get(column))
            if value and value not in parts:
                parts.append(value)
    else:
        for column, value in row.items():
            if (
                column == "source_row"
                or column in name_columns
                or column in email_columns
            ):
                continue
            text = _stringify_value(value)
            if text and text not in parts:
                parts.append(text)

    for code_column in code_columns:
        code_value = _stringify_value(row.get(code_column))
        if code_value and code_value not in parts:
            parts.insert(0, code_value)
            break

    if not parts:
        return name
    return " | ".join(parts)


def _resolve_email(
    row: dict[str, Any],
    email_columns: list[str],
    name: str,
    source_row: int,
    seen_emails: set[str],
) -> str:
    explicit = ""
    for email_column in email_columns:
        explicit = _stringify_value(row.get(email_column))
        if explicit:
            break
    candidate = explicit.strip().lower()
    if not candidate or not _EMAIL_RE.fullmatch(candidate) or candidate in seen_emails:
        seed = _SLUG_RE.sub("-", name.lower()).strip("-")[:48] or "imported-record"
        candidate = f"{seed}-{source_row + 1}@import.local"
    seen_emails.add(candidate)
    return candidate


def _stringify_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore").strip()
    if isinstance(value, (str, int, float, bool)):
        return str(value).strip()
    if isinstance(value, list):
        if not value:
            return ""
        return " ".join(
            part for part in (_stringify_value(item) for item in value) if part
        )
    return json.dumps(value, ensure_ascii=False, sort_keys=True).strip()


def _count_parquet_rows(parquet_path: Path) -> int:
    pq = _require_pyarrow_parquet()
    return int(pq.ParquetFile(parquet_path).metadata.num_rows)


def _rebuild_sqlite_from_parquet(
    parquet_path: Path,
    db_path: Path,
    *,
    batch_size: int,
) -> None:
    pq = _require_pyarrow_parquet()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = db_path.with_name(f"{db_path.name}.importing")
    if temp_path.exists():
        temp_path.unlink()

    with sqlite3.connect(temp_path) as conn:
        conn.execute("PRAGMA journal_mode = OFF")
        conn.execute("PRAGMA synchronous = OFF")
        conn.execute("PRAGMA temp_store = MEMORY")
        _ensure_schema(conn)

        parquet_file = pq.ParquetFile(parquet_path)
        for batch in parquet_file.iter_batches(
            batch_size=batch_size,
            columns=["name", "email", "description", "embedding"],
        ):
            data = batch.to_pydict()
            rows = [
                (
                    str(name),
                    str(email),
                    str(description),
                    np.asarray(embedding, dtype=np.float32).tobytes(),
                )
                for name, email, description, embedding in zip(
                    data["name"],
                    data["email"],
                    data["description"],
                    data["embedding"],
                    strict=True,
                )
            ]
            conn.executemany(
                "INSERT INTO users (name, email, description, embedding) VALUES (?, ?, ?, ?)",
                rows,
            )
        conn.commit()

    os.replace(temp_path, db_path)


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            email       TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL,
            embedding   BLOB NOT NULL,
            created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _cleanup_stale_parquet_files(
    cache_dir: Path,
    source_stem: str,
    embedding_cache_key: str,
    keep_path: Path,
) -> None:
    prefix = f"{source_stem}-{embedding_cache_key}-"
    for candidate in cache_dir.glob(f"{prefix}*.parquet"):
        if candidate == keep_path:
            continue
        candidate.unlink(missing_ok=True)


def _require_polars():
    try:
        import polars as pl
    except ImportError as exc:
        raise ConfigurationError(
            "polars and pyarrow must be installed for json import"
        ) from exc
    return pl


def _require_pyarrow_parquet():
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise ConfigurationError(
            "polars and pyarrow must be installed for json import"
        ) from exc
    return pq
