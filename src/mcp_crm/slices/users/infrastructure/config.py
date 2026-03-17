"""Runtime settings for the users slice."""

from __future__ import annotations

import os
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path

import yaml  # type: ignore[import-untyped]


@dataclass(slots=True, frozen=True)
class AppConfig:
    """Static application metadata loaded from YAML."""

    name: str
    version: str
    instructions: str


@dataclass(slots=True, frozen=True)
class RuntimeConfig:
    """Runtime defaults loaded from YAML."""

    data_dir: str
    db_filename: str
    faiss_filename: str
    sqlite_timeout_seconds: int


@dataclass(slots=True, frozen=True)
class EmbeddingConfig:
    """Embedding defaults loaded from YAML."""

    model: str


@dataclass(slots=True, frozen=True)
class SearchConfig:
    """Search defaults loaded from YAML."""

    default_top_k: int
    max_top_k: int


@dataclass(slots=True, frozen=True)
class PaginationConfig:
    """Pagination defaults loaded from YAML."""

    default_limit: int
    max_limit: int


@dataclass(slots=True, frozen=True)
class TestingConfig:
    """Testing defaults loaded from YAML."""

    deterministic_embedding_dimensions: int
    docker_image: str


@dataclass(slots=True, frozen=True)
class LoggingConfig:
    """Logging defaults loaded from YAML."""

    default_format: str


@dataclass(slots=True, frozen=True)
class ProjectConfig:
    """Full project configuration loaded from YAML."""

    app: AppConfig
    runtime: RuntimeConfig
    embedding: EmbeddingConfig
    search: SearchConfig
    pagination: PaginationConfig
    testing: TestingConfig
    logging: LoggingConfig


@dataclass(slots=True, frozen=True)
class Settings:
    """Project settings loaded from environment variables."""

    root_dir: Path
    data_dir: Path
    db_path: Path
    faiss_path: Path
    sqlite_timeout_seconds: int
    embedding_model: str


def _root_dir() -> Path:
    """Return the workspace or container application root directory.

    Returns:
        The nearest parent directory that contains config/config.yaml.

    Raises:
        FileNotFoundError: If the project root cannot be resolved.
    """
    candidates = [Path.cwd(), *Path(__file__).resolve().parents]
    for candidate in candidates:
        config_path = candidate / "config" / "config.yaml"
        if config_path.exists():
            return candidate

    raise FileNotFoundError(
        "Could not locate config/config.yaml from the current runtime context."
    )


@lru_cache(maxsize=1)
def get_project_config() -> ProjectConfig:
    """Load static project configuration from YAML.

    Returns:
        Parsed project configuration.
    """
    config_path = _root_dir() / "config" / "config.yaml"
    with config_path.open("r", encoding="utf-8") as stream:
        payload = yaml.safe_load(stream)

    return ProjectConfig(
        app=AppConfig(**payload["app"]),
        runtime=RuntimeConfig(**payload["runtime"]),
        embedding=EmbeddingConfig(**payload["embedding"]),
        search=SearchConfig(**payload["search"]),
        pagination=PaginationConfig(**payload["pagination"]),
        testing=TestingConfig(**payload["testing"]),
        logging=LoggingConfig(**payload["logging"]),
    )


def get_settings() -> Settings:
    """Load runtime settings from environment variables.

    Returns:
        Immutable settings for runtime paths and model configuration.
    """
    project_config = get_project_config()
    root_dir = _root_dir()
    data_dir = root_dir / project_config.runtime.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        root_dir=root_dir,
        data_dir=data_dir,
        db_path=Path(
            os.getenv(
                "MCP_DB_PATH",
                data_dir / project_config.runtime.db_filename,
            )
        ),
        faiss_path=Path(
            os.getenv(
                "MCP_FAISS_PATH",
                data_dir / project_config.runtime.faiss_filename,
            )
        ),
        sqlite_timeout_seconds=project_config.runtime.sqlite_timeout_seconds,
        embedding_model=os.getenv(
            "MCP_EMBEDDING_MODEL",
            project_config.embedding.model,
        ),
    )
