from __future__ import annotations

from pathlib import Path

from mcp_crm.slices.users.application.crm_assistant_service import CRMAssistantService
from mcp_crm.slices.users.application.user_service import UserService
from mcp_crm.slices.users.infrastructure.embeddings import DeterministicTestEmbedder
from mcp_crm.slices.users.infrastructure.llm import StubLLMClient
from mcp_crm.slices.users.infrastructure.sqlite_repository import SQLiteUserRepository

EMBEDDING_DIMENSIONS = 16


def build_embedder() -> DeterministicTestEmbedder:
    return DeterministicTestEmbedder(dimensions=EMBEDDING_DIMENSIONS)


def build_repo(tmp_path: Path, *, name: str = "test") -> SQLiteUserRepository:
    return SQLiteUserRepository(tmp_path / f"{name}.db")


def build_service(tmp_path: Path, *, name: str = "test") -> UserService:
    return UserService(build_repo(tmp_path, name=name), build_embedder())


def build_assistant_service(
    tmp_path: Path,
    *,
    name: str = "test",
) -> CRMAssistantService:
    return CRMAssistantService(
        build_service(tmp_path, name=name),
        StubLLMClient(),
        system_prompt="You are a CRM assistant.",
    )
