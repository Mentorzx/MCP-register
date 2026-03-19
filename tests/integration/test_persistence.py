from __future__ import annotations

import sqlite3

import numpy as np
import pytest

from mcp_crm.slices.users.domain.errors import DuplicateEmailError, VectorStoreError
from mcp_crm.slices.users.infrastructure.sqlite_repository import SQLiteUserRepository
from tests.support import build_embedder, build_repo


@pytest.fixture()
def embedder():
    return build_embedder()


@pytest.fixture()
def repo(tmp_path):
    return build_repo(tmp_path)


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

    def test_persists_embedding_blob(self, tmp_path, embedder):
        db_path = tmp_path / "users.db"
        repo = SQLiteUserRepository(db_path)
        uid = repo.create_user(
            name="Ana",
            email="ana@t.com",
            description="premium client",
            embedding=embedder.embed("premium client"),
        )

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT length(embedding) FROM users WHERE id = ?",
                (uid,),
            ).fetchone()

        assert row is not None
        assert int(row[0]) > 0

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
        repo.create_user(
            name="ML",
            email="ml@t.com",
            description="machine learning engineer",
            embedding=embedder.embed("machine learning engineer"),
        )
        repo.create_user(
            name="Sales",
            email="sales@t.com",
            description="enterprise account executive",
            embedding=embedder.embed("enterprise account executive"),
        )

        hits = repo.search_users(embedder.embed("machine learning"), top_k=2)

        assert len(hits) == 2
        assert hits[0].user.name == "ML"
        assert hits[0].score >= hits[1].score

    def test_duplicate_email_raises(self, repo, embedder):
        emb = embedder.embed("test")
        repo.create_user(name="A", email="dup@t.com", description="a", embedding=emb)
        with pytest.raises(DuplicateEmailError):
            repo.create_user(
                name="B", email="dup@t.com", description="b", embedding=emb
            )

    def test_search_raises_when_embedding_blob_is_corrupted(self, tmp_path, embedder):
        db_path = tmp_path / "users.db"
        repo = SQLiteUserRepository(db_path)
        repo.create_user(
            name="Ana",
            email="ana@t.com",
            description="premium client",
            embedding=embedder.embed("premium client"),
        )

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE users SET embedding = ? WHERE email = ?",
                (b"bad", "ana@t.com"),
            )

        with pytest.raises(VectorStoreError, match="corrupted"):
            repo.search_users(embedder.embed("premium client"), top_k=1)

    def test_search_raises_when_embedding_dimensions_do_not_match(
        self,
        tmp_path,
        embedder,
    ):
        db_path = tmp_path / "users.db"
        repo = SQLiteUserRepository(db_path)
        repo.create_user(
            name="Ana",
            email="ana@t.com",
            description="premium client",
            embedding=embedder.embed("premium client"),
        )

        bad_embedding = np.asarray([1.0, 2.0], dtype=np.float32).tobytes()
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE users SET embedding = ? WHERE email = ?",
                (bad_embedding, "ana@t.com"),
            )

        with pytest.raises(VectorStoreError, match="unexpected dimensions"):
            repo.search_users(embedder.embed("premium client"), top_k=1)
