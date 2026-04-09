"""Exemplo end-to-end das tools MCP sobre uma base NCM bootstrapada.

Roda in-process via FastMCP Client (sem servidor externo).

Por padrao, usa o embedder oficial do projeto (`sentence-transformers`)
e o extrato versionado em docs/ncm_demo.json.
Se quiser apontar para o arquivo oficial baixado,
sobrescreva MCP_IMPORT_SOURCE_PATH.

Uso:
    docker run --rm -it \
    --user "$(id -u):$(id -g)" \
    -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
      -v "$(pwd)/data/runtime:/app/data/runtime" \
      mcp-crm python docs/client_example.py

    docker run --rm -it \
    --user "$(id -u):$(id -g)" \
      -e MCP_IMPORT_SOURCE_PATH=/downloads/Tabela_NCM_Vigente_20260319.json \
    -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
      -v /home/lira/Downloads:/downloads:ro \
      -v "$(pwd)/data/runtime:/app/data/runtime" \
      mcp-crm python docs/client_example.py
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastmcp import Client

from mcp_crm.drivers import mcp_server
from mcp_crm.slices.users.infrastructure.config import get_project_config


_CFG = get_project_config()
_DISABLED_VALUES = {"0", "false", "no", "off"}
_DEMO_SOURCE_PATH = Path(__file__).with_name("ncm_demo.json")
_TARGET_NCM_CODE = "0101.21.00"
_SCAN_PAGE_SIZE = 25


def _configure_demo_environment() -> None:
    os.environ.setdefault("MCP_EMBEDDING_PROVIDER", _CFG.embedding.provider)
    os.environ.setdefault("MCP_EMBEDDING_MODEL", _CFG.embedding.model)
    os.environ.setdefault("MCP_LLM_PROVIDER", "stub")

    import_enabled = os.getenv("MCP_IMPORT_ENABLED", "true").strip().lower()
    if import_enabled not in _DISABLED_VALUES:
        os.environ.setdefault(
            "MCP_IMPORT_SOURCE_PATH",
            str(_DEMO_SOURCE_PATH.resolve()),
        )


def _field(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item[name]
    return getattr(item, name)


def _compact(text: str, *, limit: int = 96) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."


def _summarize_user(item: Any) -> dict[str, Any]:
    return {
        "id": int(_field(item, "id")),
        "name": str(_field(item, "name")),
        "description": _compact(str(_field(item, "description"))),
    }


def _summarize_search_hit(item: Any) -> dict[str, Any]:
    return {
        **_summarize_user(item),
        "score": round(float(_field(item, "score")), 6),
    }


async def _find_user_by_name(
    client: Client,
    *,
    name: str,
    seed_users: list[Any],
) -> Any:
    for user in seed_users:
        if str(_field(user, "name")) == name:
            return user

    offset = len(seed_users)
    while True:
        page = await client.call_tool(
            "list_users",
            {"limit": _SCAN_PAGE_SIZE, "offset": offset},
        )
        users = list(page.data)
        if not users:
            break

        for user in users:
            if str(_field(user, "name")) == name:
                return user

        offset += len(users)
        if len(users) < _SCAN_PAGE_SIZE:
            break

    raise RuntimeError(f"Nao foi possivel localizar o NCM {name} na base importada.")


async def main() -> None:
    _configure_demo_environment()
    source_path = os.getenv("MCP_IMPORT_SOURCE_PATH", "disabled")
    embedding_provider = os.getenv("MCP_EMBEDDING_PROVIDER", _CFG.embedding.provider)
    embedding_model = os.getenv("MCP_EMBEDDING_MODEL", _CFG.embedding.model)

    async with Client(mcp_server.mcp) as client:
        print(f"bootstrap    -> source={source_path}")
        print(
            "embedding    -> " f"provider={embedding_provider} model={embedding_model}"
        )

        preview_page = await client.call_tool("list_users", {"limit": 5, "offset": 0})
        preview_users = list(preview_page.data)
        if not preview_users:
            raise RuntimeError(
                "Nenhum registro foi bootstrapado. Configure "
                "MCP_IMPORT_SOURCE_PATH com um JSON NCM valido."
            )
        print(f"list_users   -> {[_summarize_user(user) for user in preview_users]}")

        target = await _find_user_by_name(
            client,
            name=_TARGET_NCM_CODE,
            seed_users=preview_users,
        )
        target_description = str(_field(target, "description"))

        results = await client.call_tool(
            "search_users",
            {"query": target_description, "top_k": 10},
        )
        search_hits = list(results.data)
        if not search_hits:
            raise RuntimeError(
                "A busca NCM nao encontrou resultados na base bootstrapada."
            )

        target_hit = next(
            (
                hit
                for hit in search_hits
                if str(_field(hit, "name")) == _TARGET_NCM_CODE
            ),
            None,
        )
        if target_hit is None:
            raise RuntimeError(
                f"A busca NCM nao retornou {_TARGET_NCM_CODE} usando a descricao exata do item."
            )

        print(f"search_users -> {[_summarize_search_hit(hit) for hit in search_hits]}")

        found = await client.call_tool(
            "get_user",
            {"user_id": int(_field(target_hit, "id"))},
        )
        print(f"get_user     -> {_summarize_user(found.data)}")

        answer = await client.call_tool(
            "ask_crm",
            {
                "question": f"O que o NCM {_TARGET_NCM_CODE} representa na base importada?",
                "top_k": 3,
            },
        )
        answer_summary = {
            "answer": _compact(str(_field(answer.data, "answer")), limit=160),
            "matches": [
                _summarize_search_hit(hit) for hit in _field(answer.data, "matches")
            ],
        }
        print(f"ask_crm      -> {answer_summary}")

        created = await client.call_tool(
            "create_user",
            {
                "name": "Monitoramento NCM 0101.21.00",
                "email": f"ncm-monitor+{uuid4().hex[:8]}@example.com",
                "description": (
                    "Cadastro auxiliar para acompanhar o codigo 0101.21.00 "
                    "em operacoes ligadas a reprodutores de raca pura."
                ),
            },
        )
        print(f"create_user  -> id={created.data}")


if __name__ == "__main__":
    asyncio.run(main())
