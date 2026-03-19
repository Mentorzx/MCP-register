from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np

from mcp_crm.slices.users.application.ports import UserRepositoryPort
from mcp_crm.slices.users.domain.errors import DuplicateEmailError, VectorStoreError
from mcp_crm.slices.users.domain.user import SearchResult, User
from mcp_crm.slices.users.infrastructure.config import get_settings
from mcp_crm.slices.users.infrastructure.faiss_store import FaissStore
from mcp_crm.slices.users.infrastructure.logging import get_logger

logger = get_logger(__name__)

_USER_COLS = "id, name, email, description"


class SQLiteUserRepository(UserRepositoryPort):
    """SQLite + FAISS: relational source of truth with vector search."""

    def __init__(self, db_path: Path, faiss_store: FaissStore) -> None:
        settings = get_settings()
        self._db_path = db_path
        self._faiss = faiss_store
        self._timeout = settings.sqlite_timeout_seconds
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        self._sync_index()

    def create_user(
        self,
        *,
        name: str,
        email: str,
        description: str,
        embedding: list[float],
    ) -> int:
        """Persist a user row and index its embedding."""
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
        try:
            self._faiss.add(uid, embedding)
        except VectorStoreError:
            logger.exception(
                "row saved but index update failed", extra={"user_id": uid}
            )
            raise
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
        """Vector search via FAISS, then hydrate from SQLite."""
        hits = self._faiss.search(embedding, top_k)
        if not hits:
            return []
        users = self._batch_load([uid for uid, _ in hits])
        return [
            SearchResult(user=users[uid], score=score)
            for uid, score in hits
            if uid in users
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

    def _sync_index(self) -> None:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, embedding FROM users ORDER BY id"
            ).fetchall()
        pairs = [
            (int(r[0]), np.frombuffer(r[1], dtype=np.float32).tolist()) for r in rows
        ]
        self._faiss.rebuild(pairs)

    def _batch_load(self, user_ids: list[int]) -> dict[int, User]:
        ph = ", ".join("?" for _ in user_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT {_USER_COLS} FROM users WHERE id IN ({ph})", user_ids
            ).fetchall()
        return {int(r[0]): _row_to_user(r) for r in rows}

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=self._timeout)


def _row_to_user(row: tuple) -> User:
    return User(id=int(row[0]), name=row[1], email=row[2], description=row[3])
