from __future__ import annotations

import pytest

from mcp_crm.slices.users.domain.errors import (
    DuplicateEmailError,
    UserNotFoundError,
    ValidationError,
)
from mcp_crm.slices.users.infrastructure.config import get_project_config
from tests.support import build_service

_CFG = get_project_config()


@pytest.fixture()
def service(tmp_path):
    return build_service(tmp_path)


class TestCreateUser:
    def test_returns_positive_id(self, service):
        uid = service.create_user(
            name="Ana", email="ana@test.com", description="cliente vip"
        )
        assert uid > 0

    def test_strips_and_lowercases_email(self, service):
        uid = service.create_user(
            name="Bob", email="  BOB@Test.COM  ", description="lead"
        )
        user = service.get_user(user_id=uid)
        assert user.email == "bob@test.com"

    def test_strips_name_and_description(self, service):
        uid = service.create_user(
            name="  Ana  ", email="ana@test.com", description="  cliente vip  "
        )
        user = service.get_user(user_id=uid)
        assert user.name == "Ana"
        assert user.description == "cliente vip"

    def test_rejects_empty_name(self, service):
        with pytest.raises(ValidationError):
            service.create_user(name="  ", email="x@y.com", description="ok")

    def test_rejects_empty_description(self, service):
        with pytest.raises(ValidationError):
            service.create_user(name="A", email="x@y.com", description="")

    def test_rejects_invalid_email(self, service):
        with pytest.raises(ValidationError):
            service.create_user(name="A", email="not-an-email", description="ok")

    def test_rejects_duplicate_email(self, service):
        service.create_user(name="A", email="dup@t.com", description="first")
        with pytest.raises(DuplicateEmailError):
            service.create_user(name="B", email="dup@t.com", description="second")


class TestGetUser:
    def test_found(self, service):
        uid = service.create_user(name="Ana", email="ana@t.com", description="premium")
        user = service.get_user(user_id=uid)
        assert user.id == uid
        assert user.name == "Ana"

    def test_not_found(self, service):
        with pytest.raises(UserNotFoundError):
            service.get_user(user_id=999)

    def test_invalid_id(self, service):
        with pytest.raises(ValidationError):
            service.get_user(user_id=0)


class TestListUsers:
    def test_empty(self, service):
        assert service.list_users(limit=10, offset=0) == []

    def test_pagination(self, service):
        for i in range(5):
            service.create_user(
                name=f"U{i}", email=f"u{i}@t.com", description=f"desc {i}"
            )
        page = service.list_users(limit=2, offset=1)
        assert len(page) == 2
        assert page[0].name == "U1"

    def test_rejects_bad_limit(self, service):
        with pytest.raises(ValidationError):
            service.list_users(limit=0, offset=0)

    def test_rejects_limit_above_max(self, service):
        with pytest.raises(ValidationError):
            service.list_users(limit=_CFG.pagination.max_limit + 1, offset=0)

    def test_rejects_negative_offset(self, service):
        with pytest.raises(ValidationError):
            service.list_users(limit=5, offset=-1)


class TestSearchUsers:
    def test_finds_similar(self, service):
        service.create_user(
            name="Ana", email="ana@t.com", description="investimentos renda fixa"
        )
        results = service.search_users(query="renda fixa investimentos", top_k=1)
        assert len(results) == 1
        assert results[0].name == "Ana"
        assert results[0].score > 0

    def test_empty_index(self, service):
        results = service.search_users(query="qualquer coisa", top_k=5)
        assert results == []

    def test_rejects_empty_query(self, service):
        with pytest.raises(ValidationError):
            service.search_users(query="", top_k=1)

    def test_rejects_bad_top_k(self, service):
        with pytest.raises(ValidationError):
            service.search_users(query="ok", top_k=0)

    def test_rejects_top_k_above_max(self, service):
        with pytest.raises(ValidationError):
            service.search_users(query="ok", top_k=_CFG.search.max_top_k + 1)
