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
)
from mcp_crm.slices.users.infrastructure.config import get_settings
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
mcp = FastMCP("mcp-crm")


@lru_cache(maxsize=1)
def _configure_runtime() -> None:
    """Configure runtime services lazily to avoid import-time side effects."""
    configure_logging()


@lru_cache(maxsize=1)
def get_service() -> UserService:
    """Build the application lazily to avoid import-time side effects."""
    _configure_runtime()
    settings = get_settings()
    embedder = SentenceTransformerEmbedder(settings.embedding_model)
    dimensions = len(embedder.embed("dimension probe"))
    faiss_store = FaissStore(settings.faiss_path, dimensions)
    repository = SQLiteUserRepository(settings.db_path, faiss_store)
    return UserService(repository, embedder)


def _translate_error(exc: MCPCRMError) -> RuntimeError:
    logger.error(
        "Erro na operacao MCP",
        extra={"event": "mcp.error", "error": str(exc)},
    )
    return RuntimeError(str(exc))


@mcp.tool()
def create_user(name: str, email: str, description: str) -> int:
    """Create a new user."""
    try:
        service = get_service()
        user_id = service.create_user(
            name=name,
            email=email,
            description=description,
        )
        logger.info(
            "Tool create_user executada",
            extra={"event": "tool.create_user", "user_id": user_id},
        )
        return user_id
    except (ValidationError, DuplicateEmailError) as exc:
        raise _translate_error(exc) from exc


@mcp.tool()
def get_user(user_id: int) -> dict[str, object]:
    """Get a user by identifier."""
    try:
        payload = get_service().get_user(user_id=user_id)
        logger.info(
            "Tool get_user executada",
            extra={"event": "tool.get_user", "user_id": user_id},
        )
        return payload
    except (ValidationError, UserNotFoundError) as exc:
        raise _translate_error(exc) from exc


@mcp.tool()
def search_users(query: str, top_k: int = 5) -> list[dict[str, object]]:
    """Search semantically similar users."""
    try:
        payload = get_service().search_users(query=query, top_k=top_k)
        logger.info(
            "Tool search_users executada",
            extra={
                "event": "tool.search_users",
                "top_k": top_k,
                "results": len(payload),
            },
        )
        return payload
    except ValidationError as exc:
        raise _translate_error(exc) from exc


@mcp.tool()
def list_users(limit: int = 20, offset: int = 0) -> list[dict[str, object]]:
    """List users ordered by identifier."""
    try:
        payload = get_service().list_users(limit=limit, offset=offset)
        logger.info(
            "Tool list_users executada",
            extra={
                "event": "tool.list_users",
                "limit": limit,
                "offset": offset,
                "results": len(payload),
            },
        )
        return payload
    except ValidationError as exc:
        raise _translate_error(exc) from exc


def main() -> None:
    """Run the MCP server over stdio."""
    _configure_runtime()
    logger.info(
        "Iniciando servidor MCP CRM em stdio",
        extra={"event": "mcp.startup"},
    )
    mcp.run()


if __name__ == "__main__":
    main()
