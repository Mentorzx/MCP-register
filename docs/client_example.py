"""Exemplo end-to-end das tools MCP: create_user, get_user, search_users, list_users, ask_crm.

Roda in-process via FastMCP Client (sem servidor externo).

Uso:
    docker run --rm -it \\
      -e MCP_LLM_PROVIDER=stub \\
      -v "$(pwd)/data/runtime:/app/data/runtime" \\
      mcp-crm python docs/client_example.py
"""

from __future__ import annotations

import asyncio

from fastmcp import Client

from mcp_crm.drivers import mcp_server


async def main() -> None:
    async with Client(mcp_server.mcp) as c:
        # create_user
        created = await c.call_tool(
            "create_user",
            {
                "name": "Ana Silva",
                "email": "ana@example.com",
                "description": "Cliente premium interessada em investimentos.",
            },
        )
        print(f"create_user -> id={created.data}")

        # get_user
        found = await c.call_tool("get_user", {"user_id": created.data})
        print(f"get_user    -> {found.data}")

        # search_users
        results = await c.call_tool(
            "search_users",
            {"query": "cliente premium com foco em investimentos", "top_k": 2},
        )
        print(f"search_users -> {results.data}")

        # list_users
        page = await c.call_tool("list_users", {"limit": 10, "offset": 0})
        print(f"list_users  -> {page.data}")

        # ask_crm
        answer = await c.call_tool(
            "ask_crm",
            {
                "question": "Quem no CRM parece mais interessado em investimentos?",
                "top_k": 1,
            },
        )
        print(f"ask_crm     -> {answer.data}")


if __name__ == "__main__":
    asyncio.run(main())
