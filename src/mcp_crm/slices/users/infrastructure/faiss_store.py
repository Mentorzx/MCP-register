from __future__ import annotations

from pathlib import Path

import numpy as np

from mcp_crm.shared.faiss_import import import_faiss
from mcp_crm.slices.users.domain.errors import VectorStoreError
from mcp_crm.slices.users.infrastructure.logging import get_logger

logger = get_logger(__name__)


class FaissStore:
    """Persistent FAISS index keyed by user id (Inner Product)."""

    def __init__(self, index_path: Path, dimensions: int) -> None:
        self._faiss = import_faiss()
        self._index_path = index_path
        self._dimensions = dimensions
        self._index = self._load_or_create()

    def add(self, user_id: int, embedding: list[float]) -> None:
        """Index a single embedding and flush to disk."""
        vector = self._as_matrix([embedding])
        ids = np.array([user_id], dtype=np.int64)
        try:
            self._index.add_with_ids(vector, ids)
            self.save()
        except Exception as exc:
            raise VectorStoreError("could not index embedding") from exc

    def search(self, embedding: list[float], top_k: int) -> list[tuple[int, float]]:
        """Return up to top_k (user_id, score) pairs."""
        if self._index.ntotal == 0:
            return []
        query = self._as_matrix([embedding])
        try:
            distances, ids = self._index.search(query, top_k)
        except Exception as exc:
            raise VectorStoreError("search failed") from exc
        return [
            (int(uid), float(score))
            for uid, score in zip(ids[0], distances[0], strict=False)
            if int(uid) != -1
        ]

    def rebuild(self, rows: list[tuple[int, list[float]]]) -> None:
        """Drop current index and rebuild from SQLite rows."""
        self._index = self._create_index()
        try:
            if rows:
                ids = np.array([r[0] for r in rows], dtype=np.int64)
                vectors = self._as_matrix([r[1] for r in rows])
                self._index.add_with_ids(vectors, ids)
            self.save()
        except Exception as exc:
            raise VectorStoreError("rebuild failed") from exc
        logger.info(
            "index rebuilt", extra={"event": "faiss.rebuild", "rows": len(rows)}
        )

    def save(self) -> None:
        """Flush index to disk."""
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._faiss.write_index(self._index, str(self._index_path))
        except Exception as exc:
            raise VectorStoreError(f"write failed: {self._index_path}") from exc

    @property
    def exists_on_disk(self) -> bool:
        return self._index_path.exists()

    # -- private -----------------------------------------------------------

    def _load_or_create(self):
        if self._index_path.exists():
            try:
                return self._faiss.read_index(str(self._index_path))
            except Exception as exc:
                logger.warning(
                    "corrupted index, will rebuild: %s",
                    exc,
                    extra={"event": "faiss.load_failed", "path": str(self._index_path)},
                )
                return self._create_index()
        return self._create_index()

    def _create_index(self):
        return self._faiss.IndexIDMap2(self._faiss.IndexFlatIP(self._dimensions))

    def _as_matrix(self, embeddings: list[list[float]]) -> np.ndarray:
        matrix = np.asarray(embeddings, dtype=np.float32)
        if matrix.ndim != 2 or matrix.shape[1] != self._dimensions:
            raise VectorStoreError(
                f"dimension mismatch: expected {self._dimensions}, got {matrix.shape}"
            )
        return matrix
