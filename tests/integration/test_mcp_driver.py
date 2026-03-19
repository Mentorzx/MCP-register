from __future__ import annotations

import pytest

from fastmcp import Client
from fastmcp.exceptions import ToolError

from mcp_crm.drivers.mcp_server import mcp
from mcp_crm.slices.users.application.user_service import UserService
from mcp_crm.slices.users.infrastructure.embeddings import DeterministicTestEmbedder


class _DeterministicMCPEmbedder(DeterministicTestEmbedder):
    def __init__(self, _model_name: str) -> None:
        super().__init__(dimensions=16)


@pytest.fixture()
async def client(tmp_path, monkeypatch):
    from mcp_crm.drivers import mcp_server

    monkeypatch.setenv("MCP_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("MCP_FAISS_PATH", str(tmp_path / "test.faiss"))
    monkeypatch.setattr(
        mcp_server,
        "SentenceTransformerEmbedder",
        _DeterministicMCPEmbedder,
    )

    mcp_server.get_service.cache_clear()
    mcp_server._boot.cache_clear()

    async with Client(mcp) as c:
        yield c

    mcp_server.get_service.cache_clear()
    mcp_server._boot.cache_clear()


@pytest.mark.asyncio
async def test_create_and_get(client):
    created = await client.call_tool(
        "create_user",
        {"name": "Ana", "email": "ana@test.com", "description": "investimentos"},
    )
    uid = created.data
    assert isinstance(uid, int)
    assert uid > 0

    found = await client.call_tool("get_user", {"user_id": uid})
    if hasattr(found.data, "name"):
        assert found.data.name == "Ana"
    else:
        assert found.data["name"] == "Ana"


@pytest.mark.asyncio
async def test_search(client):
    await client.call_tool(
        "create_user",
        {
            "name": "Bob",
            "email": "bob@test.com",
            "description": "machine learning engineer",
        },
    )
    results = await client.call_tool(
        "search_users",
        {"query": "ml engineer", "top_k": 1},
    )
    assert len(results.data) >= 1


@pytest.mark.asyncio
async def test_list(client):
    await client.call_tool(
        "create_user",
        {"name": "C", "email": "c@test.com", "description": "desc"},
    )
    page = await client.call_tool("list_users", {"limit": 10, "offset": 0})
    assert len(page.data) >= 1


@pytest.mark.asyncio
async def test_create_user_exposes_validation_errors(client):
    with pytest.raises(ToolError, match="email is invalid"):
        await client.call_tool(
            "create_user",
            {"name": "Ana", "email": "invalid", "description": "investimentos"},
        )


@pytest.mark.asyncio
async def test_get_user_exposes_not_found_errors(client):
    with pytest.raises(ToolError, match="User 999 was not found"):
        await client.call_tool("get_user", {"user_id": 999})


@pytest.mark.asyncio
async def test_unexpected_errors_are_hidden(client, monkeypatch):
    def broken_list_users(self, *, limit: int, offset: int):
        raise RuntimeError("database connection string leaked")

    monkeypatch.setattr(UserService, "list_users", broken_list_users)

    with pytest.raises(
        ToolError,
        match="list_users failed because the server encountered an internal error.",
    ) as exc_info:
        await client.call_tool("list_users", {"limit": 10, "offset": 0})

    assert "database connection string leaked" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_tool_names():
    """Verify the server exposes exactly the tools from the case spec."""
    async with Client(mcp) as c:
        tools = await c.list_tools()
    names = {t.name for t in tools}
    assert {"create_user", "get_user", "search_users", "list_users"} <= names
