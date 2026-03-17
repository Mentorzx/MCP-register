"""Embedding providers for the users slice."""

from __future__ import annotations

import math

from mcp_crm.slices.users.application.ports import EmbeddingPort
from mcp_crm.slices.users.infrastructure.config import get_project_config


class SentenceTransformerEmbedder(EmbeddingPort):
    """Lazy wrapper over sentence-transformers."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = None

    def embed(self, text: str) -> list[float]:
        """Encode text into a normalized dense embedding.

        Args:
            text: Input text to encode.

        Returns:
            A normalized embedding vector.
        """
        model = self._get_model()
        vector = model.encode(text, normalize_embeddings=True)
        return [float(value) for value in vector.tolist()]

    def _get_model(self):
        """Load the embedding model on first use.

        Returns:
            A sentence-transformers model instance.
        """
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model


class DeterministicTestEmbedder(EmbeddingPort):
    """Fast deterministic embedder for tests and smoke checks."""

    def __init__(self, dimensions: int | None = None) -> None:
        project_config = get_project_config()
        resolved_dimensions = dimensions
        if resolved_dimensions is None:
            resolved_dimensions = (
                project_config.testing.deterministic_embedding_dimensions
            )
        self._dimensions = resolved_dimensions

    def embed(self, text: str) -> list[float]:
        """Encode text deterministically for stable tests.

        Args:
            text: Input text to encode.

        Returns:
            A normalized fixed-size embedding vector.
        """
        buckets = [0.0] * self._dimensions
        for index, byte in enumerate(text.lower().encode("utf-8")):
            buckets[index % self._dimensions] += float(byte)
        norm = math.sqrt(sum(value * value for value in buckets)) or 1.0
        return [value / norm for value in buckets]
