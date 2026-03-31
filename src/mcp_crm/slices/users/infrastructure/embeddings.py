from __future__ import annotations

import math

import numpy as np

from mcp_crm.slices.users.application.ports import EmbeddingPort
from mcp_crm.slices.users.domain.errors import ConfigurationError
from mcp_crm.slices.users.infrastructure.config import Settings, get_project_config


class SentenceTransformerEmbedder(EmbeddingPort):
    """Lazy-loaded sentence-transformers wrapper."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = None

    def embed(self, text: str) -> list[float]:
        """Return a normalized embedding for *text*."""
        model = self._ensure_model()
        vector = model.encode(text, normalize_embeddings=True)
        return [float(v) for v in vector.tolist()]

    def warm_up(self) -> list[float]:
        model = self._ensure_model()
        vector = model.encode(
            "warm up semantic search",
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vector, dtype=np.float32).tolist()

    def embed_many(
        self,
        texts: list[str],
        *,
        batch_size: int = 32,
    ) -> list[list[float]]:
        if not texts:
            return []
        model = self._ensure_model()
        vectors = model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32).tolist()

    def _ensure_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model


class DeterministicTestEmbedder(EmbeddingPort):
    """Hash-based embedder for tests — fast, no model download."""

    def __init__(self, dimensions: int | None = None) -> None:
        cfg = get_project_config()
        self._dims = dimensions or cfg.testing.deterministic_embedding_dimensions

    def embed(self, text: str) -> list[float]:
        buckets = [0.0] * self._dims
        for i, b in enumerate(text.lower().encode("utf-8")):
            buckets[i % self._dims] += float(b)
        norm = math.sqrt(sum(v * v for v in buckets)) or 1.0
        return [v / norm for v in buckets]

    def warm_up(self) -> list[float]:
        return self.embed("warm up semantic search")

    def embed_many(
        self,
        texts: list[str],
        *,
        batch_size: int = 32,
    ) -> list[list[float]]:
        del batch_size
        return [self.embed(text) for text in texts]


def build_embedder(settings: Settings) -> EmbeddingPort:
    provider = settings.embedding_provider.strip().lower()
    if provider in {"sentence-transformer", "sentence-transformers", "local"}:
        return SentenceTransformerEmbedder(settings.embedding_model)
    if provider == "deterministic":
        return DeterministicTestEmbedder()
    raise ConfigurationError(
        f"unsupported MCP_EMBEDDING_PROVIDER: {settings.embedding_provider}"
    )
