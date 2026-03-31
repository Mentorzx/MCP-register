"""MCP server driver — exposes CRM tools over stdio."""

from __future__ import annotations

import os
from functools import lru_cache

from fastmcp import FastMCP

from mcp_crm.slices.users.application.crm_assistant_service import CRMAssistantService
from mcp_crm.slices.users.application.user_service import UserService
from mcp_crm.slices.users.domain.errors import (
    ConfigurationError,
    DuplicateEmailError,
    MCPCRMError,
    UserNotFoundError,
    ValidationError,
    VectorStoreError,
)
from mcp_crm.slices.users.domain.user import (
    AskCRMResponse,
    SearchUserResponse,
    UserResponse,
)
from mcp_crm.slices.users.infrastructure.config import get_project_config, get_settings
from mcp_crm.slices.users.infrastructure.embeddings import build_embedder
from mcp_crm.slices.users.infrastructure.json_bootstrap import bootstrap_json_import
from mcp_crm.slices.users.infrastructure.llm import build_llm_client
from mcp_crm.slices.users.infrastructure.logging import configure_logging, get_logger
from mcp_crm.slices.users.infrastructure.sqlite_repository import SQLiteUserRepository

logger = get_logger(__name__)
_CFG = get_project_config()
mcp = FastMCP(
    _CFG.app.name,
    instructions=_CFG.app.instructions,
    version=_CFG.app.version,
    mask_error_details=False,
    strict_input_validation=True,
)


@lru_cache(maxsize=1)
def _boot() -> None:
    configure_logging()


@lru_cache(maxsize=1)
def get_service() -> UserService:
    """Build and cache the application service."""
    _boot()
    settings = get_settings()
    embedder = build_embedder(settings)
    warm_vector = embedder.warm_up()
    bootstrap_json_import(settings, embedder)
    repo = SQLiteUserRepository(settings.db_path)
    repo.warm_up_search_cache(expected_dimensions=len(warm_vector))
    return UserService(repo, embedder)


@lru_cache(maxsize=1)
def get_assistant_service() -> CRMAssistantService:
    """Build and cache the assistant service."""
    _boot()
    settings = get_settings()
    llm = build_llm_client(settings)
    return CRMAssistantService(
        get_service(),
        llm,
        system_prompt=settings.llm_system_prompt,
    )


def _raise_domain_error(tool_name: str, exc: MCPCRMError) -> RuntimeError:
    logger.warning(
        "Tool execution failed with a handled error.",
        extra={
            "event": "mcp.tool_error",
            "tool_name": tool_name,
            "error_type": type(exc).__name__,
            "error": str(exc),
        },
    )
    return RuntimeError(str(exc))


def _raise_unexpected_error(tool_name: str, exc: Exception) -> RuntimeError:
    logger.exception(
        "Tool execution failed with an unexpected error.",
        extra={
            "event": "mcp.tool_unexpected_error",
            "tool_name": tool_name,
            "error_type": type(exc).__name__,
        },
    )
    return RuntimeError(
        f"{tool_name} failed because the server encountered an internal error."
    )


@mcp.tool()
def create_user(name: str, email: str, description: str) -> int:
    """Create a new CRM user."""
    try:
        uid = get_service().create_user(name=name, email=email, description=description)
        logger.info("user created", extra={"event": "tool.create_user", "user_id": uid})
        return uid
    except (ValidationError, DuplicateEmailError, VectorStoreError) as exc:
        raise _raise_domain_error("create_user", exc) from exc
    except Exception as exc:
        raise _raise_unexpected_error("create_user", exc) from exc


@mcp.tool()
def get_user(user_id: int) -> UserResponse:
    """Get a user by id."""
    try:
        result = get_service().get_user(user_id=user_id)
        logger.info(
            "user fetched", extra={"event": "tool.get_user", "user_id": user_id}
        )
        return result
    except (ValidationError, UserNotFoundError) as exc:
        raise _raise_domain_error("get_user", exc) from exc
    except Exception as exc:
        raise _raise_unexpected_error("get_user", exc) from exc


@mcp.tool()
def search_users(
    query: str,
    top_k: int = _CFG.search.default_top_k,
) -> list[SearchUserResponse]:
    """Search semantically similar users."""
    try:
        results = get_service().search_users(query=query, top_k=top_k)
        logger.info(
            "search done", extra={"event": "tool.search_users", "hits": len(results)}
        )
        return results
    except (ValidationError, VectorStoreError) as exc:
        raise _raise_domain_error("search_users", exc) from exc
    except Exception as exc:
        raise _raise_unexpected_error("search_users", exc) from exc


@mcp.tool()
def list_users(
    limit: int = _CFG.pagination.default_limit,
    offset: int = 0,
) -> list[UserResponse]:
    """List users with pagination."""
    try:
        page = get_service().list_users(limit=limit, offset=offset)
        logger.info(
            "listed users", extra={"event": "tool.list_users", "count": len(page)}
        )
        return page
    except ValidationError as exc:
        raise _raise_domain_error("list_users", exc) from exc
    except Exception as exc:
        raise _raise_unexpected_error("list_users", exc) from exc


@mcp.tool()
def ask_crm(
    question: str,
    top_k: int = _CFG.search.default_top_k,
) -> AskCRMResponse:
    """Answer a CRM question grounded in the most relevant users."""
    try:
        response = get_assistant_service().ask(question=question, top_k=top_k)
        logger.info(
            "crm question answered",
            extra={
                "event": "tool.ask_crm",
                "hits": len(response.matches),
            },
        )
        return response
    except (ValidationError, VectorStoreError, ConfigurationError) as exc:
        raise _raise_domain_error("ask_crm", exc) from exc
    except Exception as exc:
        raise _raise_unexpected_error("ask_crm", exc) from exc


def main() -> None:
    try:
        _boot()
        if _should_prewarm_on_startup():
            get_service()
        logger.debug("starting mcp-crm", extra={"event": "mcp.startup"})
        mcp.run(transport="stdio", show_banner=False)
    except Exception:
        logger.exception(
            "Failed to start MCP CRM.",
            extra={"event": "mcp.startup_failed"},
        )
        raise


def _should_prewarm_on_startup() -> bool:
    raw = os.getenv("MCP_PREWARM_ON_STARTUP", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


if __name__ == "__main__":
    main()
