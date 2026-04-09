from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke


def _run(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> str:
    completed = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout


def _image_exists(image_tag: str, *, cwd: Path) -> bool:
    completed = subprocess.run(
        ["docker", "image", "inspect", image_tag],
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
    )
    return completed.returncode == 0


def _docker_user_args() -> list[str]:
    getuid = getattr(os, "getuid", None)
    getgid = getattr(os, "getgid", None)
    if getuid is None or getgid is None:
        return []
    return ["--user", f"{getuid()}:{getgid()}"]


@pytest.mark.skipif(
    os.getenv("RUN_DOCKER_SMOKE") != "1",
    reason="set RUN_DOCKER_SMOKE=1 to run Docker E2E smoke tests",
)
def test_docker_image_exercises_all_tools(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    image_tag = os.getenv("DOCKER_SMOKE_IMAGE", "mcp-crm:latest")
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    demo_source = repo_root / "docs" / "ncm_demo.json"
    demo_payload = json.loads(demo_source.read_text(encoding="utf-8"))
    expected_rows = len(demo_payload["Nomenclaturas"]) + 1

    if not _image_exists(image_tag, cwd=repo_root):
        _run(["docker", "build", "-t", image_tag, "."], cwd=repo_root)

    output = _run(
        [
            "docker",
            "run",
            "--rm",
            *_docker_user_args(),
            "-e",
            "MCP_EMBEDDING_PROVIDER=deterministic",
            "-e",
            "MCP_LLM_PROVIDER=stub",
            "-e",
            "PYTHONPATH=/app/src",
            "-v",
            f"{repo_root}:/app",
            "-w",
            "/app",
            "-v",
            f"{runtime_dir}:/app/data/runtime",
            image_tag,
            "/opt/venv/bin/python",
            "docs/client_example.py",
        ],
        cwd=repo_root,
    )

    assert "bootstrap    -> source=" in output
    assert "list_users   ->" in output
    assert "search_users ->" in output
    assert "get_user     ->" in output
    assert "ask_crm      ->" in output
    assert "create_user  -> id=" in output
    assert "0101.21.00" in output
    assert (runtime_dir / "users.db").exists()
    assert not (runtime_dir / "users.faiss").exists()

    persisted = _run(
        [
            "docker",
            "run",
            "--rm",
            *_docker_user_args(),
            "-v",
            f"{repo_root}:/app",
            "-w",
            "/app",
            "-v",
            f"{runtime_dir}:/app/data/runtime",
            image_tag,
            "/opt/venv/bin/python",
            "-c",
            (
                "import sqlite3; "
                "conn = sqlite3.connect('/app/data/runtime/users.db'); "
                "row = conn.execute("
                "'SELECT COUNT(*), COUNT(embedding) FROM users "
                "WHERE embedding IS NOT NULL'"
                ").fetchone(); "
                "print(f'{row[0]}:{row[1]}')"
            ),
        ],
        cwd=repo_root,
    ).strip()

    assert persisted == f"{expected_rows}:{expected_rows}"
