"""FAISS import helper adapted from PFF shared utilities."""

from __future__ import annotations

import warnings
from typing import Any


def import_faiss() -> Any:
    """Import FAISS while silencing noisy third-party deprecations."""
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                category=DeprecationWarning,
                message=r".*numpy\\.core\\._multiarray_umath.*",
            )
            warnings.filterwarnings(
                "ignore",
                category=DeprecationWarning,
                message=r".*SwigPyPacked.*__module__.*",
            )
            warnings.filterwarnings(
                "ignore",
                category=DeprecationWarning,
                message=r".*SwigPyObject.*__module__.*",
            )
            warnings.filterwarnings(
                "ignore",
                category=DeprecationWarning,
                message=r".*swigvarlink.*__module__.*",
            )
            import faiss

        return faiss
    except Exception as exc:
        raise RuntimeError(f"Failed to import FAISS: {exc}") from exc
