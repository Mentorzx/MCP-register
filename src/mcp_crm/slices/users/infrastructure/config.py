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
    sqlite_timeout_seconds: int


@dataclass(slots=True, frozen=True)
class EmbeddingConfig:
    provider: str
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
class LLMConfig:
    provider: str
    model: str
    base_url: str
    timeout_seconds: int
    system_prompt: str


@dataclass(slots=True, frozen=True)
class ProjectConfig:
    app: AppConfig
    runtime: RuntimeConfig
    embedding: EmbeddingConfig
    search: SearchConfig
    pagination: PaginationConfig
    testing: TestingConfig
    logging: LoggingConfig
    llm: LLMConfig


@dataclass(slots=True, frozen=True)
class Settings:
    root_dir: Path
    data_dir: Path
    db_path: Path
    sqlite_timeout_seconds: int
    embedding_model: str
    embedding_provider: str
    llm_provider: str
    llm_model: str
    llm_base_url: str
    llm_api_key: str | None
    llm_timeout_seconds: int
    llm_system_prompt: str


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
        llm=LLMConfig(**raw["llm"]),
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
        sqlite_timeout_seconds=cfg.runtime.sqlite_timeout_seconds,
        embedding_model=os.getenv("MCP_EMBEDDING_MODEL", cfg.embedding.model),
        embedding_provider=os.getenv("MCP_EMBEDDING_PROVIDER", cfg.embedding.provider),
        llm_provider=os.getenv("MCP_LLM_PROVIDER", cfg.llm.provider),
        llm_model=os.getenv("MCP_LLM_MODEL", cfg.llm.model),
        llm_base_url=os.getenv("MCP_LLM_BASE_URL", cfg.llm.base_url),
        llm_api_key=os.getenv("MCP_LLM_API_KEY"),
        llm_timeout_seconds=int(
            os.getenv("MCP_LLM_TIMEOUT_SECONDS", str(cfg.llm.timeout_seconds))
        ),
        llm_system_prompt=os.getenv("MCP_LLM_SYSTEM_PROMPT", cfg.llm.system_prompt),
    )
