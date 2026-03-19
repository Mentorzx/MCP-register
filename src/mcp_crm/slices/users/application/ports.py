from __future__ import annotations

from typing import Protocol

from mcp_crm.slices.users.domain.user import SearchResult, User


class EmbeddingPort(Protocol):
    def embed(self, text: str) -> list[float]: ...


class UserRepositoryPort(Protocol):
    def create_user(
        self,
        *,
        name: str,
        email: str,
        description: str,
        embedding: list[float],
    ) -> int: ...

    def get_user(self, user_id: int) -> User | None: ...

    def list_users(self, *, limit: int, offset: int) -> list[User]: ...

    def search_users(
        self, embedding: list[float], *, top_k: int
    ) -> list[SearchResult]: ...
