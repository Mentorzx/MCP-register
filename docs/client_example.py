from __future__ import annotations

import asyncio

from fastmcp import Client

from mcp_crm.drivers import mcp_server


async def main() -> None:
    async with Client(mcp_server.mcp) as client:
        created = await client.call_tool(
            "create_user",
            {
                "name": "Ana Silva",
                "email": "ana@example.com",
                "description": "Cliente premium interessada em investimentos.",
            },
        )
        found = await client.call_tool("get_user", {"user_id": created.data})
        results = await client.call_tool(
            "search_users",
            {"query": "cliente premium com foco em investimentos", "top_k": 1},
        )

        print(created.data)
        print(found.data)
        print(results.data)


if __name__ == "__main__":
    asyncio.run(main())
