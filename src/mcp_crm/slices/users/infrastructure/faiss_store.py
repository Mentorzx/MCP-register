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
        """Add a single embedding to the FAISS index and persist it.

        Args:
            user_id: Persistent identifier mapped to the embedding.
            embedding: Dense embedding vector.

        Raises:
            VectorStoreError: If the index cannot be updated or saved.
        """
        vector = self._as_matrix([embedding])
        ids = np.array([user_id], dtype=np.int64)
        try:
            self._index.add_with_ids(vector, ids)
            self.save()
        except Exception as exc:
            raise VectorStoreError(
                "Failed to update the FAISS index with the new user embedding."
            ) from exc

    def search(
        self,
        embedding: list[float],
        top_k: int,
    ) -> list[tuple[int, float]]:
        """Search the FAISS index.

        Args:
            embedding: Dense query embedding.
            top_k: Maximum number of hits to return.

        Returns:
            A list of user id and score tuples.

        Raises:
            VectorStoreError: If the search fails.
        """
        if self._index.ntotal == 0:
            return []
        query = self._as_matrix([embedding])
        try:
            distances, ids = self._index.search(query, top_k)
        except Exception as exc:
            raise VectorStoreError(
                "Failed to search the FAISS index."
            ) from exc
        results: list[tuple[int, float]] = []
        for user_id, score in zip(ids[0], distances[0], strict=False):
            if int(user_id) == -1:
                continue
            results.append((int(user_id), float(score)))
        return results

    def rebuild(self, rows: list[tuple[int, list[float]]]) -> None:
        """Rebuild the FAISS index from persisted embeddings.

        Args:
            rows: Stored user ids and embeddings loaded from SQLite.

        Raises:
            VectorStoreError: If the rebuild cannot be completed.
        """
        self._index = self._create_index()
        try:
            if rows:
                ids = np.array([row[0] for row in rows], dtype=np.int64)
                vectors = self._as_matrix([row[1] for row in rows])
                self._index.add_with_ids(vectors, ids)
            self.save()
        except Exception as exc:
            raise VectorStoreError(
                "Failed to rebuild the FAISS index from persisted embeddings."
            ) from exc
        logger.info(
            "Rebuilt the FAISS index from SQLite.",
            extra={"event": "faiss.rebuild", "rows": len(rows)},
        )

    def save(self) -> None:
        """Persist the current index to disk.

        Raises:
            VectorStoreError: If the index cannot be written to disk.
        """
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._faiss.write_index(self._index, str(self._index_path))
        except Exception as exc:
            raise VectorStoreError(
                "Failed to persist the FAISS index."
            ) from exc

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
                        "Failed to load the persisted FAISS index; "
                        "a rebuild will be attempted."
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
        """Convert embeddings to a two-dimensional float32 matrix.

        Args:
            embeddings: Dense embeddings to convert.

        Returns:
            A float32 NumPy matrix ready for FAISS.

        Raises:
            VectorStoreError: If the embedding dimensions are invalid.
        """
        matrix = np.asarray(embeddings, dtype=np.float32)
        if matrix.ndim != 2 or matrix.shape[1] != self._dimensions:
            raise VectorStoreError(
                "Embedding dimension mismatch: "
                f"expected {self._dimensions}, got {matrix.shape}"
            )
        return matrix
