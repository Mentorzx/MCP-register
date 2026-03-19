from __future__ import annotations

import pytest

from mcp_crm.slices.users.domain.errors import DuplicateEmailError, VectorStoreError
from mcp_crm.slices.users.infrastructure.embeddings import DeterministicTestEmbedder
from mcp_crm.slices.users.infrastructure.faiss_store import FaissStore
from mcp_crm.slices.users.infrastructure.sqlite_repository import SQLiteUserRepository


@pytest.fixture()
def embedder():
    return DeterministicTestEmbedder(dimensions=16)


@pytest.fixture()
def repo(tmp_path, embedder):
    store = FaissStore(tmp_path / "test.faiss", 16)
    return SQLiteUserRepository(tmp_path / "test.db", store)


class TestSQLiteRepository:
    def test_create_and_get(self, repo, embedder):
        emb = embedder.embed("premium client")
        uid = repo.create_user(
            name="Ana", email="ana@t.com", description="premium client", embedding=emb
        )
        user = repo.get_user(uid)
        assert user is not None
        assert user.name == "Ana"
        assert user.email == "ana@t.com"

    def test_get_missing(self, repo):
        assert repo.get_user(42) is None

    def test_list_empty(self, repo):
        assert repo.list_users(limit=10, offset=0) == []

    def test_list_order(self, repo, embedder):
        for i in range(3):
            repo.create_user(
                name=f"U{i}",
                email=f"u{i}@t.com",
                description=f"desc{i}",
                embedding=embedder.embed(f"desc{i}"),
            )
        users = repo.list_users(limit=10, offset=0)
        assert [u.name for u in users] == ["U0", "U1", "U2"]

    def test_search_returns_results(self, repo, embedder):
        emb = embedder.embed("machine learning engineer")
        repo.create_user(
            name="ML", email="ml@t.com", description="ml engineer", embedding=emb
        )
        hits = repo.search_users(embedder.embed("machine learning"), top_k=1)
        assert len(hits) == 1
        assert hits[0].user.name == "ML"

    def test_duplicate_email_raises(self, repo, embedder):
        emb = embedder.embed("test")
        repo.create_user(name="A", email="dup@t.com", description="a", embedding=emb)
        with pytest.raises(DuplicateEmailError):
            repo.create_user(
                name="B", email="dup@t.com", description="b", embedding=emb
            )

    def test_rebuilds_from_sqlite_when_index_file_is_corrupted(
        self,
        tmp_path,
        embedder,
    ):
        db_path = tmp_path / "users.db"
        faiss_path = tmp_path / "users.faiss"

        repo = SQLiteUserRepository(db_path, FaissStore(faiss_path, 16))
        repo.create_user(
            name="Ana",
            email="ana@t.com",
            description="premium client",
            embedding=embedder.embed("premium client"),
        )

        faiss_path.write_bytes(b"not-a-faiss-index")

        recovered_repo = SQLiteUserRepository(db_path, FaissStore(faiss_path, 16))
        hits = recovered_repo.search_users(embedder.embed("premium client"), top_k=1)

        assert len(hits) == 1
        assert hits[0].user.email == "ana@t.com"


class TestFaissStore:
    def test_add_and_search(self, tmp_path):
        store = FaissStore(tmp_path / "idx.faiss", 4)
        store.add(1, [0.5, 0.5, 0.5, 0.5])
        hits = store.search([0.5, 0.5, 0.5, 0.5], top_k=1)
        assert len(hits) == 1
        assert hits[0][0] == 1

    def test_empty_search(self, tmp_path):
        store = FaissStore(tmp_path / "idx.faiss", 4)
        assert store.search([1, 0, 0, 0], top_k=5) == []

    def test_rebuild(self, tmp_path):
        store = FaissStore(tmp_path / "idx.faiss", 4)
        store.add(1, [1, 0, 0, 0])
        store.rebuild([(2, [0, 1, 0, 0]), (3, [0, 0, 1, 0])])
        hits = store.search([0, 1, 0, 0], top_k=1)
        assert hits[0][0] == 2

    def test_dimension_mismatch(self, tmp_path):
        store = FaissStore(tmp_path / "idx.faiss", 4)
        with pytest.raises(VectorStoreError):
            store.add(1, [1, 0])  # wrong dim

    def test_persistence(self, tmp_path):
        path = tmp_path / "idx.faiss"
        s1 = FaissStore(path, 4)
        s1.add(1, [1, 0, 0, 0])
        # reload from disk
        s2 = FaissStore(path, 4)
        hits = s2.search([1, 0, 0, 0], top_k=1)
        assert hits[0][0] == 1
