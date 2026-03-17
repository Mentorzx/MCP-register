"""Ports for users slice dependencies."""

from __future__ import annotations

from typing import Protocol

from mcp_crm.slices.users.domain.user import SearchResult, User


class EmbeddingPort(Protocol):
    """Generates embeddings for text."""

    def embed(self, text: str) -> list[float]:
        """Return a vector representation for text."""


class UserRepositoryPort(Protocol):
    """Persistence port for users."""

    def create_user(
        self,
        *,
        name: str,
        email: str,
        description: str,
        embedding: list[float],
    ) -> int:
        """Persist a user and return the generated identifier."""

    def get_user(self, user_id: int) -> User | None:
        """Return a user by identifier."""

    def list_users(self, *, limit: int, offset: int) -> list[User]:
        """Return users ordered by identifier."""

    def search_users(
        self,
        embedding: list[float],
        *,
        top_k: int,
    ) -> list[SearchResult]:
        """Return the top semantic matches."""
