from __future__ import annotations

import pytest

from mcp_crm.slices.users.application.user_service import UserService
from mcp_crm.slices.users.domain.errors import (
    UserNotFoundError,
    ValidationError,
)
from mcp_crm.slices.users.infrastructure.config import get_project_config
from mcp_crm.slices.users.infrastructure.embeddings import (
    DeterministicTestEmbedder,
)
from mcp_crm.slices.users.infrastructure.faiss_store import FaissStore
from mcp_crm.slices.users.infrastructure.sqlite_repository import (
    SQLiteUserRepository,
)


@pytest.fixture
def service(tmp_path):
    project_config = get_project_config()
    runtime = project_config.runtime
    dimensions = project_config.testing.deterministic_embedding_dimensions
    faiss_store = FaissStore(
        tmp_path / runtime.faiss_filename,
        dimensions=dimensions,
    )
    repository = SQLiteUserRepository(
        tmp_path / runtime.db_filename,
        faiss_store,
    )
    return UserService(repository, DeterministicTestEmbedder())


def test_create_and_get_user(service: UserService):
    user_id = service.create_user(
        name="Ana Silva",
        email="ana@example.com",
        description=(
            "Premium customer interested in investments and life insurance."
        ),
    )

    payload = service.get_user(user_id=user_id)

    assert payload.id == user_id
    assert payload.email == "ana@example.com"


def test_invalid_email_raises(service: UserService):
    with pytest.raises(ValidationError):
        service.create_user(name="Ana", email="invalid", description="test")


def test_missing_user_raises(service: UserService):
    with pytest.raises(UserNotFoundError):
        service.get_user(user_id=999)


def test_search_returns_ranked_results(service: UserService):
    service.create_user(
        name="Ana Silva",
        email="ana@example.com",
        description=(
            "Premium customer interested in investments and life insurance."
        ),
    )
    service.create_user(
        name="Bruno Costa",
        email="bruno@example.com",
        description="Customer focused on mortgages and credit products.",
    )

    results = service.search_users(
        query="investments and premium customer profile",
        top_k=2,
    )

    assert len(results) == 2
    assert results[0].name == "Ana Silva"
    assert results[0].score > 0


def test_list_users_applies_pagination(service: UserService):
    service.create_user(
        name="Ana Silva",
        email="ana@example.com",
        description="Premium customer.",
    )
    service.create_user(
        name="Bruno Costa",
        email="bruno@example.com",
        description="Mortgage credit customer.",
    )

    payload = service.list_users(limit=1, offset=1)

    assert len(payload) == 1
    assert payload[0].name == "Bruno Costa"
