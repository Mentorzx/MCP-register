from __future__ import annotations

import os
import subprocess
import uuid
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


@pytest.mark.skipif(
    os.getenv("RUN_DOCKER_SMOKE") != "1",
    reason="set RUN_DOCKER_SMOKE=1 to run Docker E2E smoke tests",
)
def test_docker_image_exercises_all_tools(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    image_tag = f"mcp-crm-smoke:{uuid.uuid4().hex[:8]}"
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()

    _run(["docker", "build", "-t", image_tag, "."], cwd=repo_root)

    output = _run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{runtime_dir}:/app/data/runtime",
            image_tag,
            "python",
            "docs/client_example.py",
        ],
        cwd=repo_root,
    )

    assert "create_user -> id=" in output
    assert "get_user    ->" in output
    assert "search_users ->" in output
    assert "list_users  ->" in output
    assert (runtime_dir / "users.db").exists()
    assert (runtime_dir / "users.faiss").exists()

    persisted = _run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{runtime_dir}:/app/data/runtime",
            image_tag,
            "python",
            "-c",
            (
                "import sqlite3; "
                "conn = sqlite3.connect('/app/data/runtime/users.db'); "
                "print(conn.execute('SELECT COUNT(*) FROM users').fetchone()[0])"
            ),
        ],
        cwd=repo_root,
    ).strip()

    assert persisted == "1"
