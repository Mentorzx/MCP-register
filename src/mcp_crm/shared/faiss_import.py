from __future__ import annotations

import warnings
from typing import Any


def import_faiss() -> Any:
    """Import faiss-cpu suppressing known SWIG deprecation noise."""
    try:
        with warnings.catch_warnings():
            for pat in (
                r".*numpy\\.core\\._multiarray_umath.*",
                r".*SwigPyPacked.*__module__.*",
                r".*SwigPyObject.*__module__.*",
                r".*swigvarlink.*__module__.*",
            ):
                warnings.filterwarnings(
                    "ignore", category=DeprecationWarning, message=pat
                )
            import faiss
    except Exception as exc:
        raise RuntimeError(
            "Failed to import FAISS. Check that faiss-cpu is installed for this environment."
        ) from exc
    return faiss
