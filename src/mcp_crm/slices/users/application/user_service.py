"""Use cases for the users slice."""

from __future__ import annotations

import re

from mcp_crm.slices.users.application.ports import (
    EmbeddingPort,
    UserRepositoryPort,
)
from mcp_crm.slices.users.domain.errors import (
    UserNotFoundError,
    ValidationError,
)

EMAIL_RE = re.compile(
    r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$",
    re.IGNORECASE,
)


class UserService:
    """Application facade for user operations."""

    def __init__(
        self,
        repository: UserRepositoryPort,
        embedder: EmbeddingPort,
    ) -> None:
        self._repository = repository
        self._embedder = embedder

    def create_user(self, *, name: str, email: str, description: str) -> int:
        self._validate_text(name=name, field_name="name")
        self._validate_email(email)
        self._validate_text(name=description, field_name="description")
        embedding = self._embedder.embed(description)
        return self._repository.create_user(
            name=name.strip(),
            email=email.strip().lower(),
            description=description.strip(),
            embedding=embedding,
        )

    def get_user(self, *, user_id: int) -> dict[str, object]:
        if user_id <= 0:
            raise ValidationError("user_id must be positive")
        user = self._repository.get_user(user_id)
        if user is None:
            raise UserNotFoundError(f"User {user_id} was not found")
        return self._serialize_user(user)

    def list_users(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, object]]:
        if limit <= 0 or limit > 100:
            raise ValidationError("limit must be between 1 and 100")
        if offset < 0:
            raise ValidationError("offset must be non-negative")
        users = self._repository.list_users(limit=limit, offset=offset)
        return [self._serialize_user(user) for user in users]

    def search_users(
        self,
        *,
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, object]]:
        self._validate_text(name=query, field_name="query")
        if top_k <= 0 or top_k > 100:
            raise ValidationError("top_k must be between 1 and 100")
        embedding = self._embedder.embed(query)
        results = self._repository.search_users(embedding, top_k=top_k)
        return [
            {
                **self._serialize_user(result.user),
                "score": round(float(result.score), 6),
            }
            for result in results
        ]

    @staticmethod
    def _validate_email(email: str) -> None:
        candidate = email.strip()
        if not candidate or not EMAIL_RE.fullmatch(candidate):
            raise ValidationError("email is invalid")

    @staticmethod
    def _validate_text(*, name: str, field_name: str) -> None:
        if not name or not name.strip():
            raise ValidationError(f"{field_name} must not be empty")

    @staticmethod
    def _serialize_user(user) -> dict[str, object]:
        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "description": user.description,
        }
