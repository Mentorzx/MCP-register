"""SQLite repository with FAISS-backed semantic search."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np

from mcp_crm.slices.users.application.ports import UserRepositoryPort
from mcp_crm.slices.users.domain.errors import (
    DuplicateEmailError,
    VectorStoreError,
)
from mcp_crm.slices.users.domain.user import SearchResult, User
from mcp_crm.slices.users.infrastructure.config import get_settings
from mcp_crm.slices.users.infrastructure.faiss_store import FaissStore
from mcp_crm.slices.users.infrastructure.logging import get_logger

logger = get_logger(__name__)


class SQLiteUserRepository(UserRepositoryPort):
    """SQLite persistence plus FAISS index coordination."""

    def __init__(self, db_path: Path, faiss_store: FaissStore) -> None:
        settings = get_settings()
        self._db_path = db_path
        self._faiss_store = faiss_store
        self._sqlite_timeout_seconds = settings.sqlite_timeout_seconds
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
        """Persist a user and update the vector index.

        Args:
            name: User display name.
            email: Normalized email address.
            description: CRM description.
            embedding: Dense description embedding.

        Returns:
            The newly created user id.

        Raises:
            DuplicateEmailError: If the email already exists.
            VectorStoreError: If indexing fails after persistence.
        """
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
        try:
            self._faiss_store.add(user_id, embedding)
        except VectorStoreError:
            logger.exception(
                (
                    "User persistence succeeded, but the FAISS index "
                    "update failed."
                ),
                extra={"event": "users.index_failed", "user_id": user_id},
            )
            raise
        logger.info(
            "Persisted user successfully.",
            extra={"event": "users.create", "user_id": user_id},
        )
        return user_id

    def get_user(self, user_id: int) -> User | None:
        """Return a single user by id.

        Args:
            user_id: Persistent user identifier.

        Returns:
            The matching user or None.
        """
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
        """Return a page of users ordered by id.

        Args:
            limit: Maximum number of rows to return.
            offset: Number of rows to skip.

        Returns:
            The selected page of users.
        """
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
        """Run semantic search against the FAISS index.

        Args:
            embedding: Dense query embedding.
            top_k: Maximum number of matches to return.

        Returns:
            Ranked search results for users still present in SQLite.
        """
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
        """Create the users table when it does not exist."""
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
        """Synchronize the FAISS index with SQLite contents."""
        rows = self._load_embeddings()
        self._faiss_store.rebuild(rows)

    def _load_embeddings(self) -> list[tuple[int, list[float]]]:
        """Load persisted embeddings from SQLite.

        Returns:
            Stored user ids paired with their embeddings.
        """
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, embedding FROM users ORDER BY id ASC"
            ).fetchall()
        return [
            (int(row[0]), np.frombuffer(row[1], dtype=np.float32).tolist())
            for row in rows
        ]

    def _load_users(self, user_ids: list[int]) -> dict[int, User]:
        """Load a batch of users by identifier.

        Args:
            user_ids: User identifiers to fetch.

        Returns:
            A mapping of user id to user entity.
        """
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
        """Open a SQLite connection for the repository.

        Returns:
            A SQLite connection bound to the configured database path.
        """
        return sqlite3.connect(
            self._db_path,
            timeout=self._sqlite_timeout_seconds,
        )
