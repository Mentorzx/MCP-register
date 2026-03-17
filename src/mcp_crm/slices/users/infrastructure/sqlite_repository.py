"""SQLite repository with FAISS-backed semantic search."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np

from mcp_crm.slices.users.application.ports import UserRepositoryPort
from mcp_crm.slices.users.domain.errors import DuplicateEmailError
from mcp_crm.slices.users.domain.user import SearchResult, User
from mcp_crm.slices.users.infrastructure.faiss_store import FaissStore
from mcp_crm.slices.users.infrastructure.logging import get_logger

logger = get_logger(__name__)


class SQLiteUserRepository(UserRepositoryPort):
    """SQLite persistence plus FAISS index coordination."""

    def __init__(self, db_path: Path, faiss_store: FaissStore) -> None:
        self._db_path = db_path
        self._faiss_store = faiss_store
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self._synchronize_index()

    def create_user(
        self,
        *,
        name: str,
        email: str,
        description: str,
        embedding: list[float],
    ) -> int:
        payload = np.asarray(embedding, dtype=np.float32).tobytes()
        with self._connect() as connection:
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO users (name, email, description, embedding)
                    VALUES (?, ?, ?, ?)
                    """,
                    (name, email, description, payload),
                )
            except sqlite3.IntegrityError as exc:
                raise DuplicateEmailError(
                    f"Email already exists: {email}"
                ) from exc
        if cursor.lastrowid is None:
            raise RuntimeError(
                "SQLite did not return a row id for the new user"
            )
        user_id = int(cursor.lastrowid)
        self._faiss_store.add(user_id, embedding)
        logger.info(
            "Usuario persistido com sucesso",
            extra={"event": "users.create", "user_id": user_id},
        )
        return user_id

    def get_user(self, user_id: int) -> User | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, name, email, description FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return User(
            id=int(row[0]),
            name=row[1],
            email=row[2],
            description=row[3],
        )

    def list_users(self, *, limit: int, offset: int) -> list[User]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, email, description
                FROM users
                ORDER BY id ASC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [
            User(
                id=int(row[0]),
                name=row[1],
                email=row[2],
                description=row[3],
            )
            for row in rows
        ]

    def search_users(
        self,
        embedding: list[float],
        *,
        top_k: int,
    ) -> list[SearchResult]:
        hits = self._faiss_store.search(embedding, top_k)
        if not hits:
            return []
        user_map = self._load_users([user_id for user_id, _score in hits])
        return [
            SearchResult(user=user_map[user_id], score=score)
            for user_id, score in hits
            if user_id in user_map
        ]

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def _synchronize_index(self) -> None:
        rows = self._load_embeddings()
        self._faiss_store.rebuild(rows)

    def _load_embeddings(self) -> list[tuple[int, list[float]]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, embedding FROM users ORDER BY id ASC"
            ).fetchall()
        return [
            (int(row[0]), np.frombuffer(row[1], dtype=np.float32).tolist())
            for row in rows
        ]

    def _load_users(self, user_ids: list[int]) -> dict[int, User]:
        placeholders = ", ".join("?" for _ in user_ids)
        with self._connect() as connection:
            rows = connection.execute(
                (
                    "SELECT id, name, email, description "
                    f"FROM users WHERE id IN ({placeholders})"
                ),
                user_ids,
            ).fetchall()
        return {
            int(row[0]): User(
                id=int(row[0]),
                name=row[1],
                email=row[2],
                description=row[3],
            )
            for row in rows
        }

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)
