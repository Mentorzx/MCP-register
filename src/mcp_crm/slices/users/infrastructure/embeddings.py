from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path

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
            _prepare_sentence_transformers_runtime()
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


def _prepare_sentence_transformers_runtime() -> None:
    cache_dir = _resolve_writable_cache_dir(
        "TORCHINDUCTOR_CACHE_DIR",
        _default_torchinductor_cache_dir(),
    )
    os.environ["TORCHINDUCTOR_CACHE_DIR"] = str(cache_dir)

    huggingface_home = _resolve_writable_cache_dir(
        "HF_HOME",
        _default_huggingface_cache_dir(),
    )
    os.environ["HF_HOME"] = str(huggingface_home)

    huggingface_hub_cache = _resolve_writable_cache_dir(
        "HF_HUB_CACHE",
        huggingface_home / "hub",
    )
    os.environ["HF_HUB_CACHE"] = str(huggingface_hub_cache)
    os.environ["TRANSFORMERS_CACHE"] = str(
        _resolve_writable_cache_dir(
            "TRANSFORMERS_CACHE",
            huggingface_hub_cache,
        )
    )

    if not os.getenv("HOME"):
        os.environ["HOME"] = tempfile.gettempdir()

    if _current_uid_has_passwd_entry():
        return

    fallback_user = f"uid-{os.getuid()}"
    os.environ.setdefault("USER", fallback_user)
    os.environ.setdefault("LOGNAME", fallback_user)


def _default_torchinductor_cache_dir() -> Path:
    return (
        Path(tempfile.gettempdir()) / "mcp-crm" / "torchinductor" / f"uid-{os.getuid()}"
    )


def _default_huggingface_cache_dir() -> Path:
    return (
        Path(tempfile.gettempdir()) / "mcp-crm" / "huggingface" / f"uid-{os.getuid()}"
    )


def _current_uid_has_passwd_entry() -> bool:
    try:
        import pwd
    except ImportError:
        return True

    try:
        pwd.getpwuid(os.getuid())
    except KeyError:
        return False
    return True


def _resolve_writable_cache_dir(env_name: str, default_path: Path) -> Path:
    raw = os.getenv(env_name)
    if raw and raw.strip():
        candidate = Path(raw.strip())
        if _ensure_directory(candidate):
            return candidate
    if _ensure_directory(default_path):
        return default_path
    raise PermissionError(f"no writable cache directory available for {env_name}")


def _ensure_directory(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return path.is_dir() and os.access(path, os.W_OK | os.X_OK)
