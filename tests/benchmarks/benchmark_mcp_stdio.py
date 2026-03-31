from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE_ROOT))
sys.path.insert(0, str(WORKSPACE_ROOT / "src"))

from fastmcp import Client  # noqa: E402

from tests.support import build_service  # noqa: E402


def _description_for_index(index: int) -> str:
    topics = [
        "machine learning platform",
        "enterprise sales operations",
        "wealth management advisory",
        "industrial robotics maintenance",
        "logistics planning and routing",
        "animal health compliance",
        "pharmaceutical quality assurance",
        "retail demand forecasting",
    ]
    region = ["norte", "sul", "leste", "oeste"][index % 4]
    detail = index // len(topics)
    return f"{topics[index % len(topics)]} batch {detail} {region}"


def _p95(values: list[float]) -> float:
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[94]


async def _measure_tool(
    client: Client, tool_name: str, payload: dict[str, object], *, runs: int
) -> list[float]:
    durations: list[float] = []
    for _ in range(runs):
        started = time.perf_counter()
        await client.call_tool(tool_name, payload)
        durations.append((time.perf_counter() - started) * 1000)
    return durations


def _server_config(db_path: Path) -> dict[str, object]:
    return {
        "command": str(WORKSPACE_ROOT / ".venv" / "bin" / "python"),
        "args": ["-m", "mcp_crm.drivers.mcp_server"],
        "cwd": str(WORKSPACE_ROOT),
        "env": {
            "PYTHONPATH": str(WORKSPACE_ROOT / "src"),
            "MCP_DB_PATH": str(db_path),
            "MCP_EMBEDDING_PROVIDER": "deterministic",
            "MCP_LLM_PROVIDER": "stub",
        },
    }


async def _run(size: int, top_k: int, warm_runs: int, runs: int) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="mcp-stdio-bench-") as tmp_dir:
        runtime_root = Path(tmp_dir)
        service = build_service(runtime_root, name="mcp-stdio")
        for index in range(size):
            description = _description_for_index(index)
            service.create_user(
                name=f"U{index}",
                email=f"u{index}@example.com",
                description=description,
            )

        db_path = runtime_root / "mcp-stdio.db"
        client_config = {"mcpServers": {"mcp-crm": _server_config(db_path)}}

        init_started = time.perf_counter()
        async with Client(client_config, init_timeout=20, timeout=20) as client:
            init_ms = (time.perf_counter() - init_started) * 1000
            tools = await client.list_tools()
            tool_names = sorted(tool.name for tool in tools)

            search_payload = {
                "query": "industrial robotics maintenance oeste",
                "top_k": top_k,
            }
            ask_payload = {
                "question": "Quem parece mais ligado a industrial robotics maintenance?",
                "top_k": top_k,
            }

            first_search_ms = (
                await _measure_tool(client, "search_users", search_payload, runs=1)
            )[0]
            await _measure_tool(client, "search_users", search_payload, runs=warm_runs)
            measured_search = await _measure_tool(
                client,
                "search_users",
                search_payload,
                runs=runs,
            )
            measured_ask = await _measure_tool(
                client, "ask_crm", ask_payload, runs=max(1, runs // 2)
            )
            create_ms = (
                await _measure_tool(
                    client,
                    "create_user",
                    {
                        "name": "Tail User",
                        "email": f"tail+{uuid4().hex[:8]}@example.com",
                        "description": "industrial robotics maintenance expansion oeste",
                    },
                    runs=1,
                )
            )[0]

        return {
            "dataset_size": size,
            "top_k": top_k,
            "tool_count": len(tool_names),
            "tool_names": tool_names,
            "init_ms": round(init_ms, 3),
            "first_search_ms": round(first_search_ms, 3),
            "search_ms": {
                "min": round(min(measured_search), 3),
                "median": round(statistics.median(measured_search), 3),
                "p95": round(_p95(measured_search), 3),
                "max": round(max(measured_search), 3),
            },
            "ask_crm_ms": {
                "min": round(min(measured_ask), 3),
                "median": round(statistics.median(measured_ask), 3),
                "p95": round(_p95(measured_ask), 3),
                "max": round(max(measured_ask), 3),
            },
            "create_user_ms": round(create_ms, 3),
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark do servidor MCP em stdio real usando FastMCP Client."
    )
    parser.add_argument(
        "--size", type=int, default=500, help="Quantidade de registros na base."
    )
    parser.add_argument(
        "--top-k", type=int, default=5, help="Quantidade de resultados por busca."
    )
    parser.add_argument(
        "--warm-runs", type=int, default=3, help="Buscas de aquecimento."
    )
    parser.add_argument("--runs", type=int, default=10, help="Buscas medidas.")
    args = parser.parse_args()

    report = asyncio.run(
        _run(
            size=args.size,
            top_k=args.top_k,
            warm_runs=args.warm_runs,
            runs=args.runs,
        )
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
