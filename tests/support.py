from __future__ import annotations

from pathlib import Path

from mcp_crm.slices.users.application.user_service import UserService
from mcp_crm.slices.users.infrastructure.embeddings import DeterministicTestEmbedder
from mcp_crm.slices.users.infrastructure.faiss_store import FaissStore
from mcp_crm.slices.users.infrastructure.sqlite_repository import SQLiteUserRepository

EMBEDDING_DIMENSIONS = 16


class DeterministicMCPEmbedder(DeterministicTestEmbedder):
    def __init__(self, _model_name: str) -> None:
        super().__init__(dimensions=EMBEDDING_DIMENSIONS)


def build_embedder() -> DeterministicTestEmbedder:
    return DeterministicTestEmbedder(dimensions=EMBEDDING_DIMENSIONS)


def build_repo(tmp_path: Path, *, name: str = "test") -> SQLiteUserRepository:
    store = FaissStore(tmp_path / f"{name}.faiss", EMBEDDING_DIMENSIONS)
    return SQLiteUserRepository(tmp_path / f"{name}.db", store)


def build_service(tmp_path: Path, *, name: str = "test") -> UserService:
    return UserService(build_repo(tmp_path, name=name), build_embedder())
