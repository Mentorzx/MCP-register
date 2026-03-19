from __future__ import annotations

import re

from mcp_crm.slices.users.application.ports import EmbeddingPort, UserRepositoryPort
from mcp_crm.slices.users.domain.errors import UserNotFoundError, ValidationError
from mcp_crm.slices.users.domain.user import SearchUserResponse, User, UserResponse
from mcp_crm.slices.users.infrastructure.config import get_project_config

_CFG = get_project_config()

_EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.IGNORECASE)


class UserService:
    """Application facade for user operations."""

    def __init__(self, repository: UserRepositoryPort, embedder: EmbeddingPort) -> None:
        self._repo = repository
        self._embedder = embedder

    def create_user(self, *, name: str, email: str, description: str) -> int:
        """Validate inputs, generate embedding and persist the user."""
        self._require_text(name, "name")
        self._check_email(email)
        self._require_text(description, "description")
        embedding = self._embedder.embed(description)
        return self._repo.create_user(
            name=name.strip(),
            email=email.strip().lower(),
            description=description.strip(),
            embedding=embedding,
        )

    def get_user(self, *, user_id: int) -> UserResponse:
        """Fetch a single user by id or raise."""
        if user_id <= 0:
            raise ValidationError("user_id must be positive")
        user = self._repo.get_user(user_id)
        if user is None:
            raise UserNotFoundError(f"User {user_id} was not found")
        return _to_response(user)

    def list_users(
        self,
        *,
        limit: int = _CFG.pagination.default_limit,
        offset: int = 0,
    ) -> list[UserResponse]:
        """Return a paginated slice of users."""
        max_limit = _CFG.pagination.max_limit
        if limit <= 0 or limit > max_limit:
            raise ValidationError(f"limit must be between 1 and {max_limit}")
        if offset < 0:
            raise ValidationError("offset must be non-negative")
        return [
            _to_response(u) for u in self._repo.list_users(limit=limit, offset=offset)
        ]

    def search_users(
        self,
        *,
        query: str,
        top_k: int = _CFG.search.default_top_k,
    ) -> list[SearchUserResponse]:
        """Encode query and search persisted embeddings for similar users."""
        self._require_text(query, "query")
        max_top_k = _CFG.search.max_top_k
        if top_k <= 0 or top_k > max_top_k:
            raise ValidationError(f"top_k must be between 1 and {max_top_k}")
        embedding = self._embedder.embed(query)
        return [
            SearchUserResponse(
                id=r.user.id,
                name=r.user.name,
                email=r.user.email,
                description=r.user.description,
                score=round(float(r.score), 6),
            )
            for r in self._repo.search_users(embedding, top_k=top_k)
        ]

    @staticmethod
    def _check_email(email: str) -> None:
        candidate = email.strip()
        if not candidate or not _EMAIL_RE.fullmatch(candidate):
            raise ValidationError("email is invalid")

    @staticmethod
    def _require_text(value: str, field: str) -> None:
        if not value or not value.strip():
            raise ValidationError(f"{field} must not be empty")


def _to_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id, name=user.name, email=user.email, description=user.description
    )
