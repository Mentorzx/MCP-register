from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import numpy as np

from mcp_crm.slices.users.infrastructure.config import Settings
from mcp_crm.slices.users.infrastructure.embeddings import DeterministicTestEmbedder
from mcp_crm.slices.users.infrastructure.json_bootstrap import bootstrap_json_import


def _build_settings(tmp_path: Path) -> Settings:
    runtime_dir = tmp_path / "runtime"
    return Settings(
        root_dir=tmp_path,
        data_dir=runtime_dir,
        db_path=runtime_dir / "users.db",
        sqlite_timeout_seconds=30,
        json_import_enabled=True,
        json_import_dir=runtime_dir / "import",
        json_import_cache_dir=runtime_dir / "import-cache",
        json_import_source_path=None,
        json_import_batch_size=2,
        search_cache_enabled=True,
        embedding_model="deterministic",
        embedding_provider="deterministic",
        llm_provider="stub",
        llm_model="gpt-4.1-mini",
        llm_base_url="https://api.openai.com/v1",
        llm_api_key=None,
        llm_timeout_seconds=30,
        llm_system_prompt="stub",
    )


def test_bootstrap_json_import_builds_parquet_and_sqlite(tmp_path):
    settings = _build_settings(tmp_path)
    settings.json_import_dir.mkdir(parents=True)
    source_path = settings.json_import_dir / "ncm.json"
    source_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "code": "0101.21.00",
                        "details": {"description": "cavalos reprodutores de raca pura vivos"},
                    },
                    {
                        "codigo": "0901.11",
                        "descricao": "cafe nao torrado nao descafeinado",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    bootstrap_json_import(settings, DeterministicTestEmbedder(dimensions=8))

    parquet_files = list(settings.json_import_cache_dir.glob("*.parquet"))
    assert settings.db_path.exists()
    assert len(parquet_files) == 1

    with sqlite3.connect(settings.db_path) as conn:
        rows = conn.execute(
            "SELECT name, email, description, embedding FROM users ORDER BY id ASC"
        ).fetchall()

    assert [row[0] for row in rows] == ["0101.21.00", "0901.11"]
    assert rows[0][1].endswith("@import.local")
    assert "cavalos" in rows[0][2]
    assert np.frombuffer(rows[0][3], dtype=np.float32).shape == (8,)


def test_bootstrap_json_import_restores_db_from_parquet_without_reembedding(tmp_path):
    class CountingEmbedder(DeterministicTestEmbedder):
        def __init__(self) -> None:
            super().__init__(dimensions=4)
            self.embed_many_calls = 0

        def embed_many(
            self,
            texts: list[str],
            *,
            batch_size: int = 32,
        ) -> list[list[float]]:
            self.embed_many_calls += 1
            return super().embed_many(texts, batch_size=batch_size)

    settings = _build_settings(tmp_path)
    settings.json_import_dir.mkdir(parents=True)
    (settings.json_import_dir / "seed.json").write_text(
        json.dumps(
            [
                {"code": "0101.21.00", "description": "cavalos vivos"},
                {"code": "0901.11", "description": "cafe cru"},
            ]
        ),
        encoding="utf-8",
    )

    first_embedder = CountingEmbedder()
    bootstrap_json_import(settings, first_embedder)
    assert first_embedder.embed_many_calls == 1

    settings.db_path.unlink()

    second_embedder = CountingEmbedder()
    bootstrap_json_import(settings, second_embedder)
    assert second_embedder.embed_many_calls == 0

    with sqlite3.connect(settings.db_path) as conn:
        row_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    assert row_count == 2


def test_bootstrap_json_import_skips_when_inbox_is_empty(tmp_path):
    settings = _build_settings(tmp_path)

    bootstrap_json_import(settings, DeterministicTestEmbedder(dimensions=8))

    assert not settings.db_path.exists()
    assert not settings.json_import_cache_dir.exists()


def test_bootstrap_json_import_rebuilds_cache_when_embedding_config_changes(tmp_path):
    class CountingEmbedder(DeterministicTestEmbedder):
        def __init__(self, dimensions: int) -> None:
            super().__init__(dimensions=dimensions)
            self.embed_many_calls = 0

        def embed_many(
            self,
            texts: list[str],
            *,
            batch_size: int = 32,
        ) -> list[list[float]]:
            self.embed_many_calls += 1
            return super().embed_many(texts, batch_size=batch_size)

    settings = _build_settings(tmp_path)
    settings.json_import_dir.mkdir(parents=True)
    (settings.json_import_dir / "seed.json").write_text(
        json.dumps([{"code": "0901.11", "description": "cafe cru"}]),
        encoding="utf-8",
    )

    first_embedder = CountingEmbedder(dimensions=4)
    bootstrap_json_import(settings, first_embedder)

    second_settings = replace(
        settings,
        embedding_provider="sentence-transformers",
        embedding_model="mini-model-v2",
    )
    second_embedder = CountingEmbedder(dimensions=4)
    bootstrap_json_import(second_settings, second_embedder)

    parquet_names = sorted(
        candidate.name for candidate in settings.json_import_cache_dir.glob("*.parquet")
    )
    assert first_embedder.embed_many_calls == 1
    assert second_embedder.embed_many_calls == 1
    assert len(parquet_names) == 2
    assert any("deterministic-deterministic" in name for name in parquet_names)
    assert any("sentence-transformers-mini-model-v2" in name for name in parquet_names)