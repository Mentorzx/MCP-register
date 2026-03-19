from __future__ import annotations

import sqlite3
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


class SQLiteUserRepository(UserRepositoryPort):
    """SQLite repository with embeddings stored in the users table."""

    def __init__(self, db_path: Path) -> None:
        settings = get_settings()
        self._db_path = db_path
        self._timeout = settings.sqlite_timeout_seconds
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
        blob = np.asarray(embedding, dtype=np.float32).tobytes()
        with self._connect() as conn:
            try:
                cur = conn.execute(
                    "INSERT INTO users (name, email, description, embedding) VALUES (?, ?, ?, ?)",
                    (name, email, description, blob),
                )
            except sqlite3.IntegrityError as exc:
                raise DuplicateEmailError(f"email already registered: {email}") from exc

        uid = int(cur.lastrowid)  # type: ignore[arg-type]
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

    def search_users(self, embedding: list[float], *, top_k: int) -> list[SearchResult]:
        """Vector search over embeddings persisted in SQLite."""
        query = _as_vector(embedding)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT {_SEARCH_COLS} FROM users ORDER BY id ASC"
            ).fetchall()
        if not rows:
            return []

        scored: list[SearchResult] = []
        for row in rows:
            user = _row_to_user(row)
            candidate = _decode_embedding(
                row[4],
                expected_dimensions=query.shape[0],
                user_id=user.id,
            )
            scored.append(
                SearchResult(
                    user=user,
                    score=float(np.dot(query, candidate)),
                )
            )
        scored.sort(key=lambda result: (-result.score, result.user.id))
        return scored[:top_k]

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
