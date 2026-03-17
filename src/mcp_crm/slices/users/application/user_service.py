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
from mcp_crm.slices.users.domain.user import (
    SearchUserResponse,
    User,
    UserResponse,
)
from mcp_crm.slices.users.infrastructure.config import get_project_config

PROJECT_CONFIG = get_project_config()

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
        """Create a user and index its semantic representation.

        Args:
            name: User display name.
            email: User email address.
            description: CRM description used for retrieval.

        Returns:
            The newly assigned user identifier.
        """
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

    def get_user(self, *, user_id: int) -> UserResponse:
        """Return a single user payload.

        Args:
            user_id: Persistent user identifier.

        Returns:
            A structured user response.

        Raises:
            ValidationError: If the identifier is invalid.
            UserNotFoundError: If the user does not exist.
        """
        if user_id <= 0:
            raise ValidationError("user_id must be positive")
        user = self._repository.get_user(user_id)
        if user is None:
            raise UserNotFoundError(f"User {user_id} was not found")
        return self._serialize_user(user)

    def list_users(
        self,
        *,
        limit: int = PROJECT_CONFIG.pagination.default_limit,
        offset: int = 0,
    ) -> list[UserResponse]:
        """Return a paginated list of users.

        Args:
            limit: Maximum number of users to return.
            offset: Number of users to skip.

        Returns:
            Structured user responses ordered by identifier.
        """
        max_limit = PROJECT_CONFIG.pagination.max_limit
        if limit <= 0 or limit > max_limit:
            raise ValidationError(
                f"limit must be between 1 and {max_limit}"
            )
        if offset < 0:
            raise ValidationError("offset must be non-negative")
        users = self._repository.list_users(limit=limit, offset=offset)
        return [self._serialize_user(user) for user in users]

    def search_users(
        self,
        *,
        query: str,
        top_k: int = PROJECT_CONFIG.search.default_top_k,
    ) -> list[SearchUserResponse]:
        """Run a semantic search over stored users.

        Args:
            query: Search text to encode.
            top_k: Maximum number of matches to return.

        Returns:
            Ranked search responses with similarity scores.
        """
        self._validate_text(name=query, field_name="query")
        max_top_k = PROJECT_CONFIG.search.max_top_k
        if top_k <= 0 or top_k > max_top_k:
            raise ValidationError(
                f"top_k must be between 1 and {max_top_k}"
            )
        embedding = self._embedder.embed(query)
        results = self._repository.search_users(embedding, top_k=top_k)
        return [
            SearchUserResponse(
                id=result.user.id,
                name=result.user.name,
                email=result.user.email,
                description=result.user.description,
                score=round(float(result.score), 6),
            )
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
    def _serialize_user(user: User) -> UserResponse:
        """Convert a persisted user into a transport-safe response.

        Args:
            user: Persisted domain entity.

        Returns:
            A structured user response.
        """
        return UserResponse(
            id=user.id,
            name=user.name,
            email=user.email,
            description=user.description,
        )
