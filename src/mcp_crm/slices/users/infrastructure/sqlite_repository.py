from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from mcp_crm.slices.users.application.ports import UserRepositoryPort
from mcp_crm.slices.users.domain.errors import DuplicateEmailError, VectorStoreError
from mcp_crm.slices.users.domain.user import SearchResult, User
from mcp_crm.slices.users.infrastructure.config import get_settings
from mcp_crm.slices.users.infrastructure.logging import get_logger

logger = get_logger(__name__)

_USER_COLS = "id, name, email, description"
_SEARCH_COLS = f"{_USER_COLS}, embedding"


@dataclass(slots=True, frozen=True)
class _SearchCache:
    users: list[User]
    user_ids: np.ndarray
    matrix: np.ndarray


class SQLiteUserRepository(UserRepositoryPort):
    """SQLite repository with embeddings stored in the users table."""

    def __init__(self, db_path: Path) -> None:
        settings = get_settings()
        self._db_path = db_path
        self._timeout = settings.sqlite_timeout_seconds
        self._cache_enabled = settings.search_cache_enabled
        self._search_cache: _SearchCache | None = None
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def create_user(
        self,
        *,
        name: str,
        email: str,
        description: str,
        embedding: list[float],
    ) -> int:
        """Persist a user row together with its embedding."""
        vector = _as_vector(embedding)
        blob = vector.tobytes()
        with self._connect() as conn:
            try:
                cur = conn.execute(
                    "INSERT INTO users (name, email, description, embedding) VALUES (?, ?, ?, ?)",
                    (name, email, description, blob),
                )
            except sqlite3.IntegrityError as exc:
                raise DuplicateEmailError(f"email already registered: {email}") from exc

        uid = int(cur.lastrowid)  # type: ignore[arg-type]
        self._refresh_search_cache_after_create(
            User(id=uid, name=name, email=email, description=description),
            vector,
        )
        logger.info("user persisted", extra={"event": "users.create", "user_id": uid})
        return uid

    def get_user(self, user_id: int) -> User | None:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT {_USER_COLS} FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return _row_to_user(row) if row else None

    def list_users(self, *, limit: int, offset: int) -> list[User]:
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT {_USER_COLS} FROM users ORDER BY id ASC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [_row_to_user(r) for r in rows]

    def search_users(
        self,
        embedding: list[float],
        *,
        top_k: int,
    ) -> list[SearchResult]:
        """Vector search over embeddings persisted in SQLite."""
        if top_k <= 0:
            return []

        query = _as_vector(embedding)
        cache = self._get_search_cache(expected_dimensions=query.shape[0])
        if not cache.users:
            return []

        scores = cache.matrix @ query
        top_indices = _select_top_indices(scores, cache.user_ids, top_k=top_k)[:top_k]

        return [
            SearchResult(user=cache.users[index], score=float(scores[index]))
            for index in top_indices.tolist()
        ]

    # -- private -----------------------------------------------------------

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
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

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=self._timeout)

    def warm_up_search_cache(self, *, expected_dimensions: int) -> None:
        self._get_search_cache(expected_dimensions=expected_dimensions)

    def _invalidate_search_cache(self) -> None:
        self._search_cache = None

    def _refresh_search_cache_after_create(
        self,
        user: User,
        embedding: np.ndarray,
    ) -> None:
        if not self._cache_enabled:
            return

        cache = self._search_cache
        if cache is None:
            return
        if cache.matrix.shape[1] != embedding.shape[0]:
            self._invalidate_search_cache()
            return

        row = embedding.reshape(1, -1)
        matrix = row.copy() if cache.matrix.size == 0 else np.concatenate((cache.matrix, row), axis=0)
        self._search_cache = _SearchCache(
            users=[*cache.users, user],
            user_ids=np.append(cache.user_ids, user.id),
            matrix=matrix,
        )

    def _get_search_cache(self, *, expected_dimensions: int) -> _SearchCache:
        if not self._cache_enabled:
            return self._load_search_cache(expected_dimensions=expected_dimensions)

        cache = self._search_cache
        if cache is not None and cache.matrix.shape[1] == expected_dimensions:
            return cache

        cache = self._load_search_cache(expected_dimensions=expected_dimensions)
        self._search_cache = cache
        return cache

    def _load_search_cache(self, *, expected_dimensions: int) -> _SearchCache:
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT {_SEARCH_COLS} FROM users ORDER BY id ASC"
            ).fetchall()

        if not rows:
            return _SearchCache(
                users=[],
                user_ids=np.empty(0, dtype=np.int64),
                matrix=np.empty((0, expected_dimensions), dtype=np.float32),
            )

        users, user_ids, matrix = _decode_search_rows(
            rows,
            expected_dimensions=expected_dimensions,
        )
        return _SearchCache(
            users=users,
            user_ids=user_ids,
            matrix=matrix,
        )


def _row_to_user(row: tuple) -> User:
    return User(id=int(row[0]), name=row[1], email=row[2], description=row[3])


def _as_vector(embedding: list[float]) -> np.ndarray:
    vector = np.asarray(embedding, dtype=np.float32)
    if vector.ndim != 1 or vector.size == 0:
        raise VectorStoreError("query embedding is invalid")
    return vector


def _decode_embedding(
    blob: bytes,
    *,
    expected_dimensions: int,
    user_id: int,
) -> np.ndarray:
    try:
        vector = np.frombuffer(blob, dtype=np.float32)
    except ValueError as exc:
        raise VectorStoreError(
            f"stored embedding for user {user_id} is corrupted"
        ) from exc
    if vector.size != expected_dimensions:
        raise VectorStoreError(
            f"stored embedding for user {user_id} has unexpected dimensions"
        )
    return vector


def _decode_search_rows(
    rows: list[tuple],
    *,
    expected_dimensions: int,
) -> tuple[
    list[User],
    np.ndarray,
    np.ndarray,
]:
    users: list[User] = []
    user_ids = np.empty(len(rows), dtype=np.int64)
    matrix = np.empty((len(rows), expected_dimensions), dtype=np.float32)

    for index, row in enumerate(rows):
        user = _row_to_user(row)
        vector = _decode_embedding(
            row[4],
            expected_dimensions=expected_dimensions,
            user_id=user.id,
        )
        users.append(user)
        user_ids[index] = user.id
        matrix[index] = vector
    return (users, user_ids, matrix)


def _select_top_indices(
    scores: np.ndarray,
    user_ids: np.ndarray,
    *,
    top_k: int,
) -> np.ndarray:
    total = scores.shape[0]
    if top_k >= total:
        return np.lexsort((user_ids, -scores))

    candidate_indices = np.argpartition(-scores, top_k - 1)[:top_k]
    cutoff_score = float(scores[candidate_indices].min())

    higher_indices = np.flatnonzero(scores > cutoff_score)
    equal_indices = np.flatnonzero(scores == cutoff_score)

    ordered_higher = _sort_indices(scores, user_ids, higher_indices)
    remaining = top_k - ordered_higher.shape[0]
    ordered_equal = _sort_indices(scores, user_ids, equal_indices)[:remaining]
    combined = np.concatenate((ordered_higher, ordered_equal))
    return _sort_indices(scores, user_ids, combined)


def _sort_indices(
    scores: np.ndarray,
    user_ids: np.ndarray,
    indices: np.ndarray,
) -> np.ndarray:
    if indices.size == 0:
        return indices
    order = np.lexsort((user_ids[indices], -scores[indices]))
    return indices[order]
