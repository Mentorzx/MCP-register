from __future__ import annotations

from mcp_crm.slices.users.infrastructure.embeddings import (
    DeterministicTestEmbedder,
)
from mcp_crm.slices.users.infrastructure.faiss_store import FaissStore
from mcp_crm.slices.users.infrastructure.sqlite_repository import (
    SQLiteUserRepository,
)


def test_repository_persists_and_rebuilds(tmp_path):
    embedder = DeterministicTestEmbedder()
    db_path = tmp_path / "users.db"
    faiss_path = tmp_path / "users.faiss"

    repository = SQLiteUserRepository(
        db_path,
        FaissStore(faiss_path, dimensions=16),
    )
    user_id = repository.create_user(
        name="Carla",
        email="carla@example.com",
        description="Perfil com interesse em previdencia privada.",
        embedding=embedder.embed(
            "Perfil com interesse em previdencia privada."
        ),
    )

    rebuilt = SQLiteUserRepository(
        db_path,
        FaissStore(faiss_path, dimensions=16),
    )
    results = rebuilt.search_users(embedder.embed("previdencia"), top_k=1)

    assert results
    assert results[0].user.id == user_id


def test_repository_rebuilds_when_index_file_is_stale(tmp_path):
    embedder = DeterministicTestEmbedder()
    db_path = tmp_path / "users.db"
    faiss_path = tmp_path / "users.faiss"

    repository = SQLiteUserRepository(
        db_path,
        FaissStore(faiss_path, dimensions=16),
    )
    user_id = repository.create_user(
        name="Daniela",
        email="daniela@example.com",
        description="Perfil com foco em investimentos internacionais.",
        embedding=embedder.embed(
            "Perfil com foco em investimentos internacionais."
        ),
    )

    stale_store = FaissStore(faiss_path, dimensions=16)
    stale_store.rebuild([])

    rebuilt = SQLiteUserRepository(
        db_path,
        FaissStore(faiss_path, dimensions=16),
    )
    results = rebuilt.search_users(embedder.embed("investimentos"), top_k=1)

    assert results
    assert results[0].user.id == user_id
