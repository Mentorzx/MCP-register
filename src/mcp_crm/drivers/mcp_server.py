"""MCP server entrypoint."""

from __future__ import annotations

from functools import lru_cache

from fastmcp import FastMCP

from mcp_crm.slices.users.application.user_service import UserService
from mcp_crm.slices.users.domain.errors import (
    DuplicateEmailError,
    MCPCRMError,
    UserNotFoundError,
    ValidationError,
    VectorStoreError,
)
from mcp_crm.slices.users.domain.user import (
    SearchUserResponse,
    UserResponse,
)
from mcp_crm.slices.users.infrastructure.config import get_settings
from mcp_crm.slices.users.infrastructure.config import get_project_config
from mcp_crm.slices.users.infrastructure.embeddings import (
    SentenceTransformerEmbedder,
)
from mcp_crm.slices.users.infrastructure.faiss_store import FaissStore
from mcp_crm.slices.users.infrastructure.logging import (
    configure_logging,
    get_logger,
)
from mcp_crm.slices.users.infrastructure.sqlite_repository import (
    SQLiteUserRepository,
)

logger = get_logger(__name__)
PROJECT_CONFIG = get_project_config()
mcp = FastMCP(
    PROJECT_CONFIG.app.name,
    instructions=PROJECT_CONFIG.app.instructions,
    version=PROJECT_CONFIG.app.version,
    mask_error_details=False,
    strict_input_validation=True,
)


@lru_cache(maxsize=1)
def _configure_runtime() -> None:
    """Configure runtime services lazily to avoid import-time side effects.

    This keeps stdio-safe imports and defers global logger setup until runtime.
    """
    configure_logging()


@lru_cache(maxsize=1)
def get_service() -> UserService:
    """Build the application lazily.

    Returns:
        A cached user service instance bound to the configured runtime.
    """
    _configure_runtime()
    settings = get_settings()
    embedder = SentenceTransformerEmbedder(settings.embedding_model)
    dimensions = len(embedder.embed("dimension probe"))
    faiss_store = FaissStore(settings.faiss_path, dimensions)
    repository = SQLiteUserRepository(settings.db_path, faiss_store)
    return UserService(repository, embedder)


def _raise_domain_error(tool_name: str, exc: MCPCRMError) -> RuntimeError:
    """Translate a known domain error into an MCP-safe exception.

    Args:
        tool_name: The tool that failed.
        exc: Domain-level exception raised during execution.

    Raises:
        RuntimeError: Always raised with a user-facing English message.
    """
    logger.warning(
        "Tool execution failed with a handled domain error.",
        extra={
            "event": "mcp.tool_error",
            "tool_name": tool_name,
            "error_type": type(exc).__name__,
            "error": str(exc),
        },
    )
    return RuntimeError(str(exc))


def _raise_unexpected_error(tool_name: str, exc: Exception) -> RuntimeError:
    """Translate an unexpected exception into an MCP-safe error.

    Args:
        tool_name: The tool that failed.
        exc: Unexpected exception raised during execution.

    Raises:
        RuntimeError: Always raised with a generic internal error message.
    """
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
    """Create a new CRM user.

    Args:
        name: User display name.
        email: User email address.
        description: Free-form CRM description.

    Returns:
        The newly created user id.
    """
    try:
        service = get_service()
        user_id = service.create_user(
            name=name,
            email=email,
            description=description,
        )
        logger.info(
            "Executed create_user successfully.",
            extra={"event": "tool.create_user", "user_id": user_id},
        )
        return user_id
    except (ValidationError, DuplicateEmailError, VectorStoreError) as exc:
        raise _raise_domain_error("create_user", exc) from exc
    except Exception as exc:
        raise _raise_unexpected_error("create_user", exc) from exc


@mcp.tool()
def get_user(user_id: int) -> UserResponse:
    """Get a user by identifier.

    Args:
        user_id: Persistent user identifier.

    Returns:
        A structured user response.
    """
    try:
        payload = get_service().get_user(user_id=user_id)
        logger.info(
            "Executed get_user successfully.",
            extra={"event": "tool.get_user", "user_id": user_id},
        )
        return payload
    except (ValidationError, UserNotFoundError) as exc:
        raise _raise_domain_error("get_user", exc) from exc
    except Exception as exc:
        raise _raise_unexpected_error("get_user", exc) from exc


@mcp.tool()
def search_users(
    query: str,
    top_k: int = PROJECT_CONFIG.search.default_top_k,
) -> list[SearchUserResponse]:
    """Search semantically similar users.

    Args:
        query: Search text to encode.
        top_k: Maximum number of matches to return.

    Returns:
        Ranked structured search results.
    """
    try:
        payload = get_service().search_users(query=query, top_k=top_k)
        logger.info(
            "Executed search_users successfully.",
            extra={
                "event": "tool.search_users",
                "top_k": top_k,
                "results": len(payload),
            },
        )
        return payload
    except (ValidationError, VectorStoreError) as exc:
        raise _raise_domain_error("search_users", exc) from exc
    except Exception as exc:
        raise _raise_unexpected_error("search_users", exc) from exc


@mcp.tool()
def list_users(
    limit: int = PROJECT_CONFIG.pagination.default_limit,
    offset: int = 0,
) -> list[UserResponse]:
    """List users ordered by identifier.

    Args:
        limit: Maximum number of users to return.
        offset: Number of users to skip.

    Returns:
        A paginated list of structured user responses.
    """
    try:
        payload = get_service().list_users(limit=limit, offset=offset)
        logger.info(
            "Executed list_users successfully.",
            extra={
                "event": "tool.list_users",
                "limit": limit,
                "offset": offset,
                "results": len(payload),
            },
        )
        return payload
    except ValidationError as exc:
        raise _raise_domain_error("list_users", exc) from exc
    except Exception as exc:
        raise _raise_unexpected_error("list_users", exc) from exc


def main() -> None:
    """Run the MCP server over stdio."""
    _configure_runtime()
    logger.info(
        "Starting MCP CRM server over stdio.",
        extra={"event": "mcp.startup"},
    )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
