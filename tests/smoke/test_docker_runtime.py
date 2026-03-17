from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
import yaml  # type: ignore[import-untyped]


pytestmark = pytest.mark.smoke


def _project_config() -> dict[str, Any]:
    config_path = _workspace_root() / "config" / "config.yaml"
    with config_path.open("r", encoding="utf-8") as stream:
        return cast(dict[str, Any], yaml.safe_load(stream))


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
    project_config = _project_config()
    if os.getenv("RUN_DOCKER_SMOKE") != "1":
        pytest.skip(
            "Set RUN_DOCKER_SMOKE=1 to enable the Docker smoke test."
        )
    if shutil.which("docker") is None:
        pytest.skip("Docker is not available in the current environment.")

    workspace_root = _workspace_root()
    image = os.getenv(
        "MCP_DOCKER_IMAGE",
        project_config["testing"]["docker_image"],
    )
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    db_filename = project_config["runtime"]["db_filename"]
    faiss_filename = project_config["runtime"]["faiss_filename"]
    dimensions = project_config["testing"][
        "deterministic_embedding_dimensions"
    ]

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
    Path('/app/data/runtime/${DB_FILENAME}'),
    FaissStore(
        Path('/app/data/runtime/${FAISS_FILENAME}'),
        dimensions=${DIMENSIONS},
    ),
)
user_id = repo.create_user(
    name='Ana Silva',
    email='ana@example.com',
    description='Premium customer interested in investments.',
    embedding=embedder.embed('Premium customer interested in investments.'),
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
    Path('/app/data/runtime/${DB_FILENAME}'),
    FaissStore(
        Path('/app/data/runtime/${FAISS_FILENAME}'),
        dimensions=${DIMENSIONS},
    ),
)
results = repo.search_users(embedder.embed('premium investments'), top_k=1)
print(json.dumps({'email': results[0].user.email, 'count': len(results)}))
"""
    create_code = (
        create_code.replace("${DB_FILENAME}", db_filename)
        .replace("${FAISS_FILENAME}", faiss_filename)
        .replace("${DIMENSIONS}", str(dimensions))
    )
    search_code = (
        search_code.replace("${DB_FILENAME}", db_filename)
        .replace("${FAISS_FILENAME}", faiss_filename)
        .replace("${DIMENSIONS}", str(dimensions))
    )

    created = _run_container(image, runtime_dir, create_code)
    queried = _run_container(image, runtime_dir, search_code)

    assert created["user_id"] == 1
    assert created["files"] == [db_filename, faiss_filename]
    assert queried == {"email": "ana@example.com", "count": 1}
