"""Ports for users slice dependencies."""

from __future__ import annotations

from typing import Protocol

from mcp_crm.slices.users.domain.user import SearchResult, User


class EmbeddingPort(Protocol):
    """Generates embeddings for text."""

    def embed(self, text: str) -> list[float]:
        """Return a vector representation for text.

        Args:
            text: Plain text input to encode.

        Returns:
            The embedding vector as a list of floats.
        """
        ...


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
        """Persist a user and return the generated identifier.

        Args:
            name: User display name.
            email: Normalized user email.
            description: Free-form CRM description.
            embedding: Dense vector representation of the description.

        Returns:
            The newly created user identifier.
        """
        ...

    def get_user(self, user_id: int) -> User | None:
        """Return a user by identifier.

        Args:
            user_id: Persistent user identifier.

        Returns:
            The matching user or None when it does not exist.
        """
        ...

    def list_users(self, *, limit: int, offset: int) -> list[User]:
        """Return users ordered by identifier.

        Args:
            limit: Maximum number of rows to return.
            offset: Number of rows to skip.

        Returns:
            The requested page of users.
        """
        ...

    def search_users(
        self,
        embedding: list[float],
        *,
        top_k: int,
    ) -> list[SearchResult]:
        """Return the top semantic matches.

        Args:
            embedding: Dense vector representation of the search query.
            top_k: Maximum number of matches to return.

        Returns:
            Ranked semantic matches ordered by relevance.
        """
        ...
