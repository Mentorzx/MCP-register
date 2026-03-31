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


def _reference_top_ids(
    records: list[tuple[int, np.ndarray]],
    query: np.ndarray,
    *,
    top_k: int,
) -> list[int]:
    scored = [
        (user_id, float(np.dot(query, embedding))) for user_id, embedding in records
    ]
    scored.sort(key=lambda item: (-item[1], item[0]))
    return [user_id for user_id, _ in scored[:top_k]]


def _description_for_index(index: int) -> str:
    topics = [
        "machine learning platform",
        "enterprise sales operations",
        "wealth management advisory",
        "industrial robotics maintenance",
        "logistics planning and routing",
        "animal health compliance",
        "pharmaceutical quality assurance",
        "retail demand forecasting",
    ]
    region = ["norte", "sul", "leste", "oeste"][index % 4]
    return f"{topics[index % len(topics)]} cohort {index // len(topics)} {region}"


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

    def test_search_matches_reference_ranking_on_large_dataset(
        self, tmp_path, embedder
    ):
        repo = build_repo(tmp_path, name="large-ranking")
        records: list[tuple[int, np.ndarray]] = []

        for index in range(512):
            description = _description_for_index(index)
            user_id = repo.create_user(
                name=f"U{index}",
                email=f"u{index}@t.com",
                description=description,
                embedding=embedder.embed(description),
            )
            records.append(
                (user_id, np.asarray(embedder.embed(description), dtype=np.float32))
            )

        query = np.asarray(
            embedder.embed("industrial robotics maintenance oeste"),
            dtype=np.float32,
        )
        expected_ids = _reference_top_ids(records, query, top_k=15)

        hits = repo.search_users(query.tolist(), top_k=15)

        assert [hit.user.id for hit in hits] == expected_ids

    def test_search_returns_all_rows_sorted_when_top_k_exceeds_dataset(
        self,
        tmp_path,
        embedder,
    ):
        repo = build_repo(tmp_path, name="top-k-overflow")
        records: list[tuple[int, np.ndarray]] = []

        for index in range(24):
            description = _description_for_index(index)
            user_id = repo.create_user(
                name=f"U{index}",
                email=f"u{index}@t.com",
                description=description,
                embedding=embedder.embed(description),
            )
            records.append(
                (user_id, np.asarray(embedder.embed(description), dtype=np.float32))
            )

        query = np.asarray(
            embedder.embed("wealth management advisory"), dtype=np.float32
        )
        expected_ids = _reference_top_ids(records, query, top_k=100)

        hits = repo.search_users(query.tolist(), top_k=100)

        assert len(hits) == 24
        assert [hit.user.id for hit in hits] == expected_ids

    def test_search_breaks_cutoff_ties_by_smallest_user_id(self, tmp_path, embedder):
        repo = build_repo(tmp_path, name="tie-cutoff")

        for index in range(8):
            description = "same ranking bucket"
            repo.create_user(
                name=f"U{index}",
                email=f"u{index}@t.com",
                description=description,
                embedding=embedder.embed(description),
            )

        hits = repo.search_users(embedder.embed("same ranking bucket"), top_k=5)

        assert [hit.user.id for hit in hits] == [1, 2, 3, 4, 5]

    def test_search_with_zero_top_k_returns_empty_list(self, repo, embedder):
        repo.create_user(
            name="Ana",
            email="ana@t.com",
            description="premium client",
            embedding=embedder.embed("premium client"),
        )

        assert repo.search_users(embedder.embed("premium client"), top_k=0) == []

    def test_search_keeps_cached_matrix_hot_after_a_new_write(
        self,
        tmp_path,
        embedder,
        monkeypatch,
    ):
        repo = build_repo(tmp_path, name="cache-reuse")
        repo.create_user(
            name="Ana",
            email="ana@t.com",
            description="premium client",
            embedding=embedder.embed("premium client"),
        )
        repo.create_user(
            name="Bob",
            email="bob@t.com",
            description="enterprise account executive",
            embedding=embedder.embed("enterprise account executive"),
        )

        calls = 0
        original = repo._load_search_cache

        def counting_loader(*, expected_dimensions: int):
            nonlocal calls
            calls += 1
            return original(expected_dimensions=expected_dimensions)

        monkeypatch.setattr(repo, "_load_search_cache", counting_loader)

        repo.search_users(embedder.embed("premium client"), top_k=1)
        repo.search_users(embedder.embed("premium client"), top_k=1)

        assert calls == 1

        repo.create_user(
            name="Carla",
            email="carla@t.com",
            description="wealth management advisory",
            embedding=embedder.embed("wealth management advisory"),
        )
        hits = repo.search_users(embedder.embed("wealth management"), top_k=2)

        assert hits[0].user.name == "Carla"
        assert calls == 1

    def test_search_empty_repository_reuses_empty_cache(
        self, tmp_path, embedder, monkeypatch
    ):
        repo = build_repo(tmp_path, name="empty-cache")

        calls = 0
        original = repo._load_search_cache

        def counting_loader(*, expected_dimensions: int):
            nonlocal calls
            calls += 1
            return original(expected_dimensions=expected_dimensions)

        monkeypatch.setattr(repo, "_load_search_cache", counting_loader)

        assert repo.search_users(embedder.embed("nobody here"), top_k=3) == []
        assert repo.search_users(embedder.embed("nobody here"), top_k=3) == []
        assert calls == 1

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
