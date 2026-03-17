"""FAISS-backed vector search for user embeddings."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from mcp_crm.shared.faiss_import import import_faiss
from mcp_crm.slices.users.domain.errors import VectorStoreError
from mcp_crm.slices.users.infrastructure.logging import get_logger

logger = get_logger(__name__)


class FaissStore:
    """Maintains a persistent FAISS index keyed by user id."""

    def __init__(self, index_path: Path, dimensions: int) -> None:
        self._faiss = import_faiss()
        self._index_path = index_path
        self._dimensions = dimensions
        self._index = self._load_or_create()

    def add(self, user_id: int, embedding: list[float]) -> None:
        vector = self._as_matrix([embedding])
        ids = np.array([user_id], dtype=np.int64)
        self._index.add_with_ids(vector, ids)
        self.save()

    def search(
        self,
        embedding: list[float],
        top_k: int,
    ) -> list[tuple[int, float]]:
        if self._index.ntotal == 0:
            return []
        query = self._as_matrix([embedding])
        distances, ids = self._index.search(query, top_k)
        results: list[tuple[int, float]] = []
        for user_id, score in zip(ids[0], distances[0], strict=False):
            if int(user_id) == -1:
                continue
            results.append((int(user_id), float(score)))
        return results

    def rebuild(self, rows: list[tuple[int, list[float]]]) -> None:
        self._index = self._create_index()
        if rows:
            ids = np.array([row[0] for row in rows], dtype=np.int64)
            vectors = self._as_matrix([row[1] for row in rows])
            self._index.add_with_ids(vectors, ids)
        self.save()
        logger.info(
            "Indice FAISS sincronizado a partir do SQLite",
            extra={"event": "faiss.rebuild", "rows": len(rows)},
        )

    def save(self) -> None:
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        self._faiss.write_index(self._index, str(self._index_path))

    @property
    def exists_on_disk(self) -> bool:
        """Return whether a persisted index file already exists."""
        return self._index_path.exists()

    def _load_or_create(self):
        if self._index_path.exists():
            try:
                return self._faiss.read_index(str(self._index_path))
            except Exception as exc:
                logger.warning(
                    (
                        "Falha ao carregar indice FAISS persistido; "
                        "um rebuild sera executado"
                    ),
                    extra={
                        "event": "faiss.load_failed",
                        "path": str(self._index_path),
                        "error": str(exc),
                    },
                )
                return self._create_index()
        return self._create_index()

    def _create_index(self):
        base_index = self._faiss.IndexFlatIP(self._dimensions)
        return self._faiss.IndexIDMap2(base_index)

    def _as_matrix(self, embeddings: list[list[float]]) -> np.ndarray:
        matrix = np.asarray(embeddings, dtype=np.float32)
        if matrix.ndim != 2 or matrix.shape[1] != self._dimensions:
            raise VectorStoreError(
                "Embedding dimension mismatch: "
                f"expected {self._dimensions}, got {matrix.shape}"
            )
        return matrix
