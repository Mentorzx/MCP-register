from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml  # type: ignore[import-untyped]


# -- config dataclasses (1:1 with config.yaml sections) --------------------


@dataclass(slots=True, frozen=True)
class AppConfig:
    name: str
    version: str
    instructions: str


@dataclass(slots=True, frozen=True)
class RuntimeConfig:
    data_dir: str
    db_filename: str
    faiss_filename: str
    sqlite_timeout_seconds: int


@dataclass(slots=True, frozen=True)
class EmbeddingConfig:
    model: str


@dataclass(slots=True, frozen=True)
class SearchConfig:
    default_top_k: int
    max_top_k: int


@dataclass(slots=True, frozen=True)
class PaginationConfig:
    default_limit: int
    max_limit: int


@dataclass(slots=True, frozen=True)
class TestingConfig:
    deterministic_embedding_dimensions: int
    docker_image: str


@dataclass(slots=True, frozen=True)
class LoggingConfig:
    default_format: str


@dataclass(slots=True, frozen=True)
class ProjectConfig:
    app: AppConfig
    runtime: RuntimeConfig
    embedding: EmbeddingConfig
    search: SearchConfig
    pagination: PaginationConfig
    testing: TestingConfig
    logging: LoggingConfig


@dataclass(slots=True, frozen=True)
class Settings:
    root_dir: Path
    data_dir: Path
    db_path: Path
    faiss_path: Path
    sqlite_timeout_seconds: int
    embedding_model: str


# -- loaders ---------------------------------------------------------------


def _root_dir() -> Path:
    """Walk up from cwd / package dir until we find config/config.yaml."""
    for candidate in [Path.cwd(), *Path(__file__).resolve().parents]:
        if (candidate / "config" / "config.yaml").exists():
            return candidate
    raise FileNotFoundError("config/config.yaml not found")


@lru_cache(maxsize=1)
def get_project_config() -> ProjectConfig:
    raw = yaml.safe_load((_root_dir() / "config" / "config.yaml").read_text("utf-8"))
    return ProjectConfig(
        app=AppConfig(**raw["app"]),
        runtime=RuntimeConfig(**raw["runtime"]),
        embedding=EmbeddingConfig(**raw["embedding"]),
        search=SearchConfig(**raw["search"]),
        pagination=PaginationConfig(**raw["pagination"]),
        testing=TestingConfig(**raw["testing"]),
        logging=LoggingConfig(**raw["logging"]),
    )


def get_settings() -> Settings:
    """Resolve runtime paths from config + env overrides."""
    cfg = get_project_config()
    root = _root_dir()
    data = root / cfg.runtime.data_dir
    data.mkdir(parents=True, exist_ok=True)
    return Settings(
        root_dir=root,
        data_dir=data,
        db_path=Path(os.getenv("MCP_DB_PATH", data / cfg.runtime.db_filename)),
        faiss_path=Path(os.getenv("MCP_FAISS_PATH", data / cfg.runtime.faiss_filename)),
        sqlite_timeout_seconds=cfg.runtime.sqlite_timeout_seconds,
        embedding_model=os.getenv("MCP_EMBEDDING_MODEL", cfg.embedding.model),
    )
