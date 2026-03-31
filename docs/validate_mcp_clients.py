from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import tomllib
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from fastmcp import Client

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TOOLS = {
    "create_user",
    "get_user",
    "search_users",
    "list_users",
    "ask_crm",
}


def _replace_workspace_token(value: str) -> str:
    return value.replace("${workspaceFolder}", str(WORKSPACE_ROOT))


def _resolve_command(value: str) -> str:
    value = _replace_workspace_token(value)
    path = Path(value)
    if path.is_absolute():
        return str(path)
    if "/" in value or value in {".", ".."}:
        return str((WORKSPACE_ROOT / value).absolute())
    return value


def _resolve_cwd(value: str) -> str:
    value = _replace_workspace_token(value)
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str((WORKSPACE_ROOT / value).absolute())


def _resolve_pythonpath(value: str) -> str:
    parts: list[str] = []
    for part in value.split(os.pathsep):
        if not part:
            continue
        resolved = _replace_workspace_token(part)
        path = Path(resolved)
        if not path.is_absolute() and part not in {".", ".."}:
            resolved = str((WORKSPACE_ROOT / part).absolute())
        parts.append(resolved)
    return os.pathsep.join(parts)


def _coerce_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _normalize_server_config(server_config: dict[str, object]) -> dict[str, object]:
    normalized = deepcopy(server_config)
    command = normalized.get("command")
    if isinstance(command, str):
        normalized["command"] = _resolve_command(command)

    cwd = normalized.get("cwd")
    if isinstance(cwd, str):
        normalized["cwd"] = _resolve_cwd(cwd)
    else:
        normalized["cwd"] = str(WORKSPACE_ROOT)

    env = _coerce_mapping(normalized.get("env"))
    resolved_env: dict[str, object] = {}
    for key, value in env.items():
        if not isinstance(key, str) or not isinstance(value, str):
            resolved_env[key] = value
            continue
        if key == "PYTHONPATH":
            resolved_env[key] = _resolve_pythonpath(value)
        else:
            resolved_env[key] = _replace_workspace_token(value)
    normalized["env"] = resolved_env
    return normalized


def _load_vscode_config() -> tuple[str, dict[str, object]]:
    config_path = WORKSPACE_ROOT / ".vscode" / "mcp.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    server = config["servers"]["mcp-crm"]
    return "vscode", _normalize_server_config(server)


def _load_codex_config() -> tuple[str, dict[str, object]]:
    config_path = WORKSPACE_ROOT / ".codex" / "config.toml"
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    server = config["mcp_servers"]["mcp_crm"]
    return "codex", _normalize_server_config(server)


def _with_test_env(
    server_name: str,
    server_config: dict[str, object],
    runtime_root: Path,
) -> dict[str, object]:
    config = deepcopy(server_config)
    env = _coerce_mapping(config.get("env"))
    env.update(
        {
            "MCP_DB_PATH": str(runtime_root / f"{server_name}.db"),
            "MCP_EMBEDDING_PROVIDER": "deterministic",
            "MCP_LLM_PROVIDER": "stub",
        }
    )
    config["env"] = env
    return config


def _extract_field(value: object, field_name: str) -> object:
    if hasattr(value, field_name):
        return getattr(value, field_name)
    if isinstance(value, dict):
        return value[field_name]
    raise TypeError(f"Could not extract '{field_name}' from {type(value)!r}")


async def _exercise_config(
    label: str,
    server_name: str,
    server_config: dict[str, object],
) -> None:
    client_config = {"mcpServers": {server_name: server_config}}
    async with Client(client_config, init_timeout=20, timeout=20) as client:
        tools = {tool.name for tool in await client.list_tools()}
        missing = EXPECTED_TOOLS - tools
        if missing:
            raise AssertionError(f"{label}: missing tools {sorted(missing)}")

        email = f"ana+{uuid4().hex[:8]}@example.com"
        created = await client.call_tool(
            "create_user",
            {
                "name": "Ana Silva",
                "email": email,
                "description": "Cliente premium interessada em investimentos.",
            },
        )
        user_id = created.data
        if not isinstance(user_id, int) or user_id <= 0:
            raise AssertionError(
                f"{label}: create_user returned invalid id {user_id!r}"
            )

        found = await client.call_tool("get_user", {"user_id": user_id})
        found_name = _extract_field(found.data, "name")
        if found_name != "Ana Silva":
            raise AssertionError(
                f"{label}: get_user returned unexpected name {found_name!r}"
            )

        results = await client.call_tool(
            "search_users",
            {"query": "cliente premium interessada em investimentos", "top_k": 1},
        )
        if len(results.data) < 1:
            raise AssertionError(f"{label}: search_users returned no matches")

        page = await client.call_tool("list_users", {"limit": 10, "offset": 0})
        if len(page.data) < 1:
            raise AssertionError(f"{label}: list_users returned no rows")

        answer = await client.call_tool(
            "ask_crm",
            {
                "question": "Quem no CRM parece mais interessado em investimentos?",
                "top_k": 1,
            },
        )
        answer_text = _extract_field(answer.data, "answer")
        if "Ana Silva" not in str(answer_text):
            raise AssertionError(
                f"{label}: ask_crm returned unexpected answer {answer_text!r}"
            )

    print(f"[{label}] ok: stdio, tools e fluxo basico funcionaram")


async def _run(target: str) -> None:
    loaders = {
        "vscode": _load_vscode_config,
        "codex": _load_codex_config,
    }
    selected = [target] if target != "all" else ["vscode", "codex"]

    with tempfile.TemporaryDirectory(prefix="mcp-clients-") as tmp_dir:
        runtime_root = Path(tmp_dir)
        for selected_target in selected:
            label, base_config = loaders[selected_target]()
            server_name = "mcp-crm" if selected_target == "vscode" else "mcp_crm"
            config = _with_test_env(
                server_name=selected_target,
                server_config=base_config,
                runtime_root=runtime_root,
            )
            await _exercise_config(label, server_name, config)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Valida as configuracoes MCP versionadas do VS Code e do Codex."
    )
    parser.add_argument(
        "--target",
        choices=["all", "vscode", "codex"],
        default="all",
        help="Config alvo a validar.",
    )
    args = parser.parse_args()

    try:
        asyncio.run(_run(args.target))
    except KeyboardInterrupt:
        print("Interrompido.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Falha na validacao MCP: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
