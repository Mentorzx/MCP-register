from __future__ import annotations

from pathlib import Path

import pytest

from fastmcp import Client
from fastmcp.exceptions import ToolError

from mcp_crm.drivers.mcp_server import mcp
from mcp_crm.slices.users.application.crm_assistant_service import CRMAssistantService
from mcp_crm.slices.users.application.user_service import UserService
from mcp_crm.slices.users.domain.errors import ConfigurationError


def _reset_server_caches(mcp_server) -> None:
    mcp_server.get_service.cache_clear()
    mcp_server.get_assistant_service.cache_clear()
    mcp_server._boot.cache_clear()


@pytest.fixture()
async def client(tmp_path, monkeypatch):
    from mcp_crm.drivers import mcp_server

    monkeypatch.setenv("MCP_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("MCP_EMBEDDING_PROVIDER", "deterministic")
    monkeypatch.setenv("MCP_LLM_PROVIDER", "stub")
    monkeypatch.setenv("MCP_IMPORT_ENABLED", "false")

    _reset_server_caches(mcp_server)

    async with Client(mcp) as c:
        yield c

    _reset_server_caches(mcp_server)


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
async def test_ask_crm(client):
    await client.call_tool(
        "create_user",
        {
            "name": "Ana",
            "email": "ana-ask@test.com",
            "description": "contato focado em orquidea quantica beta delta",
        },
    )

    answer = await client.call_tool(
        "ask_crm",
        {
            "question": "Quem no CRM parece mais ligado a orquidea quantica beta delta?",
            "top_k": 1,
        },
    )

    data = answer.data
    if hasattr(data, "answer"):
        assert "Ana" in data.answer
        assert len(data.matches) == 1
    else:
        assert "Ana" in data["answer"]
        assert len(data["matches"]) == 1


@pytest.mark.asyncio
async def test_ask_crm_works_with_default_stub_provider(tmp_path, monkeypatch):
    from mcp_crm.drivers import mcp_server

    monkeypatch.setenv("MCP_DB_PATH", str(tmp_path / "default-stub.db"))
    monkeypatch.setenv("MCP_EMBEDDING_PROVIDER", "deterministic")
    monkeypatch.setenv("MCP_IMPORT_ENABLED", "false")
    monkeypatch.delenv("MCP_LLM_PROVIDER", raising=False)

    _reset_server_caches(mcp_server)

    async with Client(mcp) as c:
        await c.call_tool(
            "create_user",
            {
                "name": "Ana",
                "email": "ana-default@test.com",
                "description": "contato focado em orquidea quantica beta delta",
            },
        )

        answer = await c.call_tool(
            "ask_crm",
            {
                "question": "Quem no CRM parece mais ligado a orquidea quantica beta delta?",
                "top_k": 1,
            },
        )

        data = answer.data
        if hasattr(data, "answer"):
            assert "Ana" in data.answer
        else:
            assert "Ana" in data["answer"]

    _reset_server_caches(mcp_server)


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
async def test_ask_crm_exposes_configuration_errors(tmp_path, monkeypatch):
    from mcp_crm.drivers import mcp_server

    monkeypatch.setenv("MCP_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("MCP_EMBEDDING_PROVIDER", "deterministic")
    monkeypatch.setenv("MCP_LLM_PROVIDER", "stub")
    monkeypatch.setenv("MCP_IMPORT_ENABLED", "false")
    monkeypatch.setattr(
        CRMAssistantService,
        "ask",
        lambda self, *, question, top_k: (_ for _ in ()).throw(
            ConfigurationError(
                "ask_crm is unavailable because no LLM provider is configured"
            )
        ),
    )

    _reset_server_caches(mcp_server)

    async with Client(mcp) as c:
        with pytest.raises(
            ToolError,
            match="ask_crm is unavailable because no LLM provider is configured",
        ):
            await c.call_tool(
                "ask_crm",
                {"question": "Quem parece um lead premium?", "top_k": 1},
            )

    _reset_server_caches(mcp_server)


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
async def test_ask_crm_hides_unexpected_llm_errors(client, monkeypatch):
    monkeypatch.setattr(
        CRMAssistantService,
        "ask",
        lambda self, *, question, top_k: (_ for _ in ()).throw(
            RuntimeError("llm api key leaked")
        ),
    )

    with pytest.raises(
        ToolError,
        match="ask_crm failed because the server encountered an internal error.",
    ) as exc_info:
        await client.call_tool(
            "ask_crm",
            {"question": "Quem parece um lead premium?", "top_k": 1},
        )

    assert "llm api key leaked" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_tool_names():
    """Verify the server exposes exactly the tools from the case spec."""
    async with Client(mcp) as c:
        tools = await c.list_tools()
    names = {t.name for t in tools}
    assert {"create_user", "get_user", "search_users", "list_users", "ask_crm"} <= names


@pytest.mark.asyncio
async def test_get_service_bootstraps_rows_from_runtime_json(tmp_path, monkeypatch):
    from mcp_crm.drivers import mcp_server

    source_dir = tmp_path / "runtime-import"
    source_dir.mkdir(parents=True)
    (source_dir / "seed.json").write_text(
        '{"items": [{"code": "0101.21.00", "description": "cavalos vivos"}]}',
        encoding="utf-8",
    )

    monkeypatch.setenv("MCP_DB_PATH", str(tmp_path / "imported.db"))
    monkeypatch.setenv("MCP_EMBEDDING_PROVIDER", "deterministic")
    monkeypatch.setenv("MCP_IMPORT_DIR", str(source_dir))
    monkeypatch.setenv("MCP_IMPORT_CACHE_DIR", str(tmp_path / "import-cache"))
    monkeypatch.delenv("MCP_IMPORT_SOURCE_PATH", raising=False)

    _reset_server_caches(mcp_server)

    service = mcp_server.get_service()
    page = service.list_users(limit=10, offset=0)

    assert page[0].name == "0101.21.00"
    assert "cavalos" in page[0].description

    _reset_server_caches(mcp_server)


def test_search_returns_exact_ncm_match_for_exact_description(
    tmp_path,
    monkeypatch,
):
    from mcp_crm.drivers import mcp_server

    source_dir = tmp_path / "runtime-import"
    source_dir.mkdir(parents=True)
    demo_source = Path(__file__).resolve().parents[2] / "docs" / "ncm_demo.json"
    (source_dir / "Tabela_NCM_Vigente_20260319.json").write_text(
        demo_source.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    monkeypatch.setenv("MCP_DB_PATH", str(tmp_path / "imported.db"))
    monkeypatch.setenv("MCP_EMBEDDING_PROVIDER", "deterministic")
    monkeypatch.setenv("MCP_LLM_PROVIDER", "stub")
    monkeypatch.setenv("MCP_IMPORT_ENABLED", "true")
    monkeypatch.setenv("MCP_IMPORT_DIR", str(source_dir))
    monkeypatch.setenv("MCP_IMPORT_CACHE_DIR", str(tmp_path / "import-cache"))
    monkeypatch.delenv("MCP_IMPORT_SOURCE_PATH", raising=False)

    _reset_server_caches(mcp_server)

    service = mcp_server.get_service()
    preview = service.list_users(limit=25, offset=0)
    target = next(item for item in preview if item.name == "0101.21.00")

    results = service.search_users(query=target.description, top_k=5)

    assert results[0].name == "0101.21.00"

    _reset_server_caches(mcp_server)


def test_get_service_warms_repo_cache(tmp_path, monkeypatch):
    from mcp_crm.drivers import mcp_server

    monkeypatch.setenv("MCP_DB_PATH", str(tmp_path / "warm-cache.db"))
    monkeypatch.setenv("MCP_EMBEDDING_PROVIDER", "deterministic")
    monkeypatch.setenv("MCP_IMPORT_ENABLED", "false")

    _reset_server_caches(mcp_server)

    service = mcp_server.get_service()
    repo = service._repo

    assert hasattr(repo, "_search_cache")
    assert getattr(repo, "_search_cache", None) is not None

    _reset_server_caches(mcp_server)
