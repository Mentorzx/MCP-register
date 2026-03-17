from __future__ import annotations

import asyncio

import pytest
from fastmcp import Client

from mcp_crm.drivers import mcp_server


class StubUserService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def create_user(self, *, name: str, email: str, description: str) -> int:
        self.calls.append(
            (
                "create_user",
                {
                    "name": name,
                    "email": email,
                    "description": description,
                },
            )
        )
        return 101

    def get_user(self, *, user_id: int) -> dict[str, object]:
        self.calls.append(("get_user", {"user_id": user_id}))
        return {
            "id": user_id,
            "name": "Ana Silva",
            "email": "ana@example.com",
            "description": "Cliente premium.",
        }

    def search_users(
        self,
        *,
        query: str,
        top_k: int,
    ) -> list[dict[str, object]]:
        self.calls.append(("search_users", {"query": query, "top_k": top_k}))
        return [
            {
                "id": 101,
                "name": "Ana Silva",
                "email": "ana@example.com",
                "description": "Cliente premium.",
                "score": 0.99,
            }
        ]

    def list_users(
        self,
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, object]]:
        self.calls.append(("list_users", {"limit": limit, "offset": offset}))
        return [
            {
                "id": 101,
                "name": "Ana Silva",
                "email": "ana@example.com",
                "description": "Cliente premium.",
            }
        ]


def _run(coro):
    return asyncio.run(coro)


async def _list_tools() -> list:
    async with Client(mcp_server.mcp) as client:
        return await client.list_tools()


def test_mcp_server_registers_expected_tools():
    tools = _run(_list_tools())
    tool_map = {tool.name: tool for tool in tools}

    assert set(tool_map) >= {
        "create_user",
        "get_user",
        "search_users",
        "list_users",
    }
    assert set(tool_map["create_user"].inputSchema["properties"]) == {
        "name",
        "email",
        "description",
    }
    assert set(tool_map["search_users"].inputSchema["properties"]) == {
        "query",
        "top_k",
    }


def test_mcp_server_tools_delegate_to_service(monkeypatch: pytest.MonkeyPatch):
    stub = StubUserService()
    mcp_server.get_service.cache_clear()
    monkeypatch.setattr(mcp_server, "get_service", lambda: stub)

    created = mcp_server.create_user(
        name="Ana Silva",
        email="ana@example.com",
        description="Cliente premium.",
    )
    found = mcp_server.get_user(user_id=101)
    results = mcp_server.search_users(query="cliente premium", top_k=1)
    listed = mcp_server.list_users(limit=10, offset=0)

    assert created == 101
    assert found["email"] == "ana@example.com"
    assert results[0]["score"] == 0.99
    assert listed[0]["id"] == 101
    assert stub.calls == [
        (
            "create_user",
            {
                "name": "Ana Silva",
                "email": "ana@example.com",
                "description": "Cliente premium.",
            },
        ),
        ("get_user", {"user_id": 101}),
        ("search_users", {"query": "cliente premium", "top_k": 1}),
        ("list_users", {"limit": 10, "offset": 0}),
    ]
