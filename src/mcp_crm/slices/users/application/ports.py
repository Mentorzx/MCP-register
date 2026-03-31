from __future__ import annotations

from typing import Protocol

from mcp_crm.slices.users.domain.user import SearchResult, User


class EmbeddingPort(Protocol):
    def embed(self, text: str) -> list[float]: ...

    def warm_up(self) -> list[float]: ...

    def embed_many(
        self,
        texts: list[str],
        *,
        batch_size: int = 32,
    ) -> list[list[float]]: ...


class LLMPort(Protocol):
    def generate(self, *, system_prompt: str, prompt: str) -> str: ...


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
        self,
        embedding: list[float],
        *,
        top_k: int,
    ) -> list[SearchResult]: ...
