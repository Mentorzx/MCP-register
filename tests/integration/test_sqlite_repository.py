from __future__ import annotations

from mcp_crm.slices.users.infrastructure.embeddings import (
    DeterministicTestEmbedder,
)
from mcp_crm.slices.users.infrastructure.config import get_project_config
from mcp_crm.slices.users.infrastructure.faiss_store import FaissStore
from mcp_crm.slices.users.infrastructure.sqlite_repository import (
    SQLiteUserRepository,
)


def test_repository_persists_and_rebuilds(tmp_path):
    project_config = get_project_config()
    dimensions = project_config.testing.deterministic_embedding_dimensions
    embedder = DeterministicTestEmbedder()
    db_path = tmp_path / project_config.runtime.db_filename
    faiss_path = tmp_path / project_config.runtime.faiss_filename

    repository = SQLiteUserRepository(
        db_path,
        FaissStore(faiss_path, dimensions=dimensions),
    )
    user_id = repository.create_user(
        name="Carla",
        email="carla@example.com",
        description="Profile interested in retirement planning.",
        embedding=embedder.embed("Profile interested in retirement planning."),
    )

    rebuilt = SQLiteUserRepository(
        db_path,
        FaissStore(faiss_path, dimensions=dimensions),
    )
    results = rebuilt.search_users(embedder.embed("retirement"), top_k=1)

    assert results
    assert results[0].user.id == user_id


def test_repository_rebuilds_when_index_file_is_stale(tmp_path):
    project_config = get_project_config()
    dimensions = project_config.testing.deterministic_embedding_dimensions
    embedder = DeterministicTestEmbedder()
    db_path = tmp_path / project_config.runtime.db_filename
    faiss_path = tmp_path / project_config.runtime.faiss_filename

    repository = SQLiteUserRepository(
        db_path,
        FaissStore(faiss_path, dimensions=dimensions),
    )
    user_id = repository.create_user(
        name="Daniela",
        email="daniela@example.com",
        description="Profile focused on international investments.",
        embedding=embedder.embed(
            "Profile focused on international investments."
        ),
    )

    stale_store = FaissStore(faiss_path, dimensions=dimensions)
    stale_store.rebuild([])

    rebuilt = SQLiteUserRepository(
        db_path,
        FaissStore(faiss_path, dimensions=dimensions),
    )
    results = rebuilt.search_users(embedder.embed("investments"), top_k=1)

    assert results
    assert results[0].user.id == user_id
