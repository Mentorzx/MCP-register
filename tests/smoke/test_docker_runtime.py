from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _image_exists(image: str) -> bool:
    command = ["docker", "image", "inspect", image]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _ensure_image(image: str, workspace_root: Path) -> None:
    if _image_exists(image):
        return
    subprocess.run(
        ["docker", "build", "-t", image, "."],
        cwd=workspace_root,
        check=True,
    )


def _run_container(
    image: str,
    runtime_dir: Path,
    code: str,
) -> dict[str, object]:
    command = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{runtime_dir}:/app/data/runtime",
        image,
        "python",
        "-c",
        code,
    ]
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout.strip())


def test_docker_persists_runtime_data_between_runs(tmp_path: Path):
    if os.getenv("RUN_DOCKER_SMOKE") != "1":
        pytest.skip(
            "Defina RUN_DOCKER_SMOKE=1 para habilitar o smoke test Docker"
        )
    if shutil.which("docker") is None:
        pytest.skip("Docker nao esta disponivel no ambiente")

    workspace_root = _workspace_root()
    image = os.getenv("MCP_DOCKER_IMAGE", "mcp-crm:latest")
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()

    _ensure_image(image, workspace_root)

    create_code = """import json
from pathlib import Path

from mcp_crm.slices.users.infrastructure.embeddings import (
    DeterministicTestEmbedder,
)
from mcp_crm.slices.users.infrastructure.faiss_store import FaissStore
from mcp_crm.slices.users.infrastructure.sqlite_repository import (
    SQLiteUserRepository,
)

embedder = DeterministicTestEmbedder()
repo = SQLiteUserRepository(
    Path('/app/data/runtime/users.db'),
    FaissStore(Path('/app/data/runtime/users.faiss'), dimensions=16),
)
user_id = repo.create_user(
    name='Ana Silva',
    email='ana@example.com',
    description='Cliente premium interessada em investimentos.',
    embedding=embedder.embed('Cliente premium interessada em investimentos.'),
)
payload = {
    'user_id': user_id,
    'files': sorted(p.name for p in Path('/app/data/runtime').iterdir()),
}
print(json.dumps(payload))
"""
    search_code = """import json
from pathlib import Path

from mcp_crm.slices.users.infrastructure.embeddings import (
    DeterministicTestEmbedder,
)
from mcp_crm.slices.users.infrastructure.faiss_store import FaissStore
from mcp_crm.slices.users.infrastructure.sqlite_repository import (
    SQLiteUserRepository,
)

embedder = DeterministicTestEmbedder()
repo = SQLiteUserRepository(
    Path('/app/data/runtime/users.db'),
    FaissStore(Path('/app/data/runtime/users.faiss'), dimensions=16),
)
results = repo.search_users(embedder.embed('investimentos premium'), top_k=1)
print(json.dumps({'email': results[0].user.email, 'count': len(results)}))
"""

    created = _run_container(image, runtime_dir, create_code)
    queried = _run_container(image, runtime_dir, search_code)

    assert created["user_id"] == 1
    assert created["files"] == ["users.db", "users.faiss"]
    assert queried == {"email": "ana@example.com", "count": 1}
