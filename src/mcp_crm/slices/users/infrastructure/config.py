from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml  # type: ignore[import-untyped]

_RUNTIME_FALLBACK_DIR = Path(".tmp") / "runtime"


# -- config dataclasses (1:1 with config.yaml sections) --------------------


@dataclass(slots=True, frozen=True)
class AppConfig:
    name: str
    version: str
    instructions: str


@dataclass(slots=True, frozen=True)
class RuntimeConfig:
    data_dir: str
    db_filename: str
    sqlite_timeout_seconds: int


@dataclass(slots=True, frozen=True)
class EmbeddingConfig:
    provider: str
    model: str


@dataclass(slots=True, frozen=True)
class SearchConfig:
    default_top_k: int
    max_top_k: int


@dataclass(slots=True, frozen=True)
class PaginationConfig:
    default_limit: int
    max_limit: int


@dataclass(slots=True, frozen=True)
class TestingConfig:
    deterministic_embedding_dimensions: int
    docker_image: str


@dataclass(slots=True, frozen=True)
class LoggingConfig:
    default_format: str


@dataclass(slots=True, frozen=True)
class LLMConfig:
    provider: str
    model: str
    base_url: str
    timeout_seconds: int
    system_prompt: str


@dataclass(slots=True, frozen=True)
class ProjectConfig:
    app: AppConfig
    runtime: RuntimeConfig
    embedding: EmbeddingConfig
    search: SearchConfig
    pagination: PaginationConfig
    testing: TestingConfig
    logging: LoggingConfig
    llm: LLMConfig


@dataclass(slots=True, frozen=True)
class Settings:
    root_dir: Path
    data_dir: Path
    db_path: Path
    sqlite_timeout_seconds: int
    json_import_enabled: bool
    json_import_dir: Path
    json_import_cache_dir: Path
    json_import_source_path: Path | None
    json_import_batch_size: int
    search_cache_enabled: bool
    embedding_model: str
    embedding_provider: str
    llm_provider: str
    llm_model: str
    llm_base_url: str
    llm_api_key: str | None
    llm_timeout_seconds: int
    llm_system_prompt: str


# -- loaders ---------------------------------------------------------------


def _root_dir() -> Path:
    """Walk up from cwd / package dir until we find config/config.yaml."""
    for candidate in [Path.cwd(), *Path(__file__).resolve().parents]:
        if (candidate / "config" / "config.yaml").exists():
            return candidate
    raise FileNotFoundError("config/config.yaml not found")


@lru_cache(maxsize=1)
def get_project_config() -> ProjectConfig:
    raw = yaml.safe_load((_root_dir() / "config" / "config.yaml").read_text("utf-8"))
    return ProjectConfig(
        app=AppConfig(**raw["app"]),
        runtime=RuntimeConfig(**raw["runtime"]),
        embedding=EmbeddingConfig(**raw["embedding"]),
        search=SearchConfig(**raw["search"]),
        pagination=PaginationConfig(**raw["pagination"]),
        testing=TestingConfig(**raw["testing"]),
        logging=LoggingConfig(**raw["logging"]),
        llm=LLMConfig(**raw["llm"]),
    )


def get_settings() -> Settings:
    """Resolve runtime paths from config + env overrides."""
    cfg = get_project_config()
    root = _root_dir()
    data = _resolve_runtime_dir(root, cfg.runtime.data_dir)
    import_enabled_raw = os.getenv("MCP_IMPORT_ENABLED", "true").strip().lower()
    cache_enabled_raw = os.getenv("MCP_SEARCH_CACHE_ENABLED", "true").strip().lower()
    return Settings(
        root_dir=root,
        data_dir=data,
        db_path=_resolve_env_path(
            "MCP_DB_PATH",
            _resolve_db_path(root, data, cfg.runtime.db_filename),
            root=root,
        ),
        sqlite_timeout_seconds=cfg.runtime.sqlite_timeout_seconds,
        json_import_enabled=import_enabled_raw not in {"0", "false", "no", "off"},
        json_import_dir=_resolve_env_path(
            "MCP_IMPORT_DIR",
            data / "import",
            root=root,
        ),
        json_import_cache_dir=_resolve_env_path(
            "MCP_IMPORT_CACHE_DIR",
            data / "import-cache",
            root=root,
        ),
        json_import_source_path=_resolve_optional_env_path(
            "MCP_IMPORT_SOURCE_PATH",
            root=root,
        ),
        json_import_batch_size=max(
            1,
            int(os.getenv("MCP_IMPORT_BATCH_SIZE", "256")),
        ),
        search_cache_enabled=cache_enabled_raw not in {"0", "false", "no", "off"},
        embedding_model=os.getenv("MCP_EMBEDDING_MODEL", cfg.embedding.model),
        embedding_provider=os.getenv("MCP_EMBEDDING_PROVIDER", cfg.embedding.provider),
        llm_provider=os.getenv("MCP_LLM_PROVIDER", cfg.llm.provider),
        llm_model=os.getenv("MCP_LLM_MODEL", cfg.llm.model),
        llm_base_url=os.getenv("MCP_LLM_BASE_URL", cfg.llm.base_url),
        llm_api_key=os.getenv("MCP_LLM_API_KEY"),
        llm_timeout_seconds=int(
            os.getenv("MCP_LLM_TIMEOUT_SECONDS", str(cfg.llm.timeout_seconds))
        ),
        llm_system_prompt=os.getenv("MCP_LLM_SYSTEM_PROMPT", cfg.llm.system_prompt),
    )


def _resolve_runtime_dir(root: Path, configured_relative: str) -> Path:
    configured = root / configured_relative
    if _ensure_writable_directory(configured):
        return configured

    for fallback in _runtime_fallback_candidates(root):
        if _ensure_writable_directory(fallback):
            return fallback

    raise PermissionError(
        "no writable runtime directory available for MCP runtime data"
    )


def _resolve_db_path(root: Path, runtime_dir: Path, db_filename: str) -> Path:
    candidate = runtime_dir / db_filename
    if _is_writable_path(candidate):
        return candidate

    for fallback in _runtime_fallback_candidates(root):
        if not _ensure_writable_directory(fallback):
            continue

        fallback_candidate = fallback / db_filename
        if _is_writable_path(fallback_candidate):
            return fallback_candidate

    raise PermissionError("no writable path available for the SQLite database")


def _resolve_env_path(env_name: str, default_path: Path, *, root: Path) -> Path:
    raw = os.getenv(env_name)
    if raw is None or not raw.strip():
        return default_path
    candidate = Path(raw.strip())
    if candidate.is_absolute():
        return candidate
    return root / candidate


def _resolve_optional_env_path(env_name: str, *, root: Path) -> Path | None:
    raw = os.getenv(env_name)
    if raw is None or not raw.strip():
        return None
    candidate = Path(raw.strip())
    if candidate.is_absolute():
        return candidate
    return root / candidate


def _is_writable_directory(path: Path) -> bool:
    return path.is_dir() and os.access(path, os.W_OK | os.X_OK)


def _is_writable_path(path: Path) -> bool:
    if path.exists():
        return os.access(path, os.W_OK)
    return _is_writable_directory(path.parent)


def _ensure_writable_directory(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return _is_writable_directory(path)


def _runtime_fallback_candidates(root: Path) -> tuple[Path, ...]:
    digest = hashlib.sha1(str(root).encode("utf-8")).hexdigest()[:12]
    system_tmp = (
        Path(tempfile.gettempdir())
        / "mcp-crm-runtime"
        / f"{root.name}-{digest}"
        / "runtime"
    )
    return (root / _RUNTIME_FALLBACK_DIR, system_tmp)
