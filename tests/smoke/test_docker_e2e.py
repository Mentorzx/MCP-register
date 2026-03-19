from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
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


@pytest.mark.skipif(
    os.getenv("RUN_DOCKER_SMOKE") != "1",
    reason="set RUN_DOCKER_SMOKE=1 to run Docker E2E smoke tests",
)
def test_docker_image_exercises_all_tools(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    image_tag = os.getenv("DOCKER_SMOKE_IMAGE", "mcp-crm:latest")
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()

    if not _image_exists(image_tag, cwd=repo_root):
        _run(["docker", "build", "-t", image_tag, "."], cwd=repo_root)

    output = _run(
        [
            "docker",
            "run",
            "--rm",
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

    assert "create_user -> id=" in output
    assert "get_user    ->" in output
    assert "search_users ->" in output
    assert "list_users  ->" in output
    assert "ask_crm     ->" in output
    assert (runtime_dir / "users.db").exists()
    assert not (runtime_dir / "users.faiss").exists()

    persisted = _run(
        [
            "docker",
            "run",
            "--rm",
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
                "'SELECT COUNT(*), COUNT(embedding) FROM users WHERE embedding IS NOT NULL'"
                ").fetchone(); "
                "print(f'{row[0]}:{row[1]}')"
            ),
        ],
        cwd=repo_root,
    ).strip()

    assert persisted == "1:1"
