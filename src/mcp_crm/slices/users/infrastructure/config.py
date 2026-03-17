"""Runtime settings for the users slice."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class Settings:
    """Project settings loaded from environment variables."""

    root_dir: Path
    data_dir: Path
    db_path: Path
    faiss_path: Path
    embedding_model: str


def get_settings() -> Settings:
    root_dir = Path(__file__).resolve().parents[5]
    data_dir = root_dir / "data" / "runtime"
    data_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        root_dir=root_dir,
        data_dir=data_dir,
        db_path=Path(os.getenv("MCP_DB_PATH", data_dir / "users.db")),
        faiss_path=Path(os.getenv("MCP_FAISS_PATH", data_dir / "users.faiss")),
        embedding_model=os.getenv(
            "MCP_EMBEDDING_MODEL",
            "sentence-transformers/all-MiniLM-L6-v2",
        ),
    )
