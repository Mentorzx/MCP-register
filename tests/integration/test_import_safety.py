from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_importing_mcp_server_has_no_runtime_side_effects(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    db_path = runtime_dir / "users.db"
    faiss_path = runtime_dir / "users.faiss"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    env["MCP_DB_PATH"] = str(db_path)
    env["MCP_FAISS_PATH"] = str(faiss_path)

    script = """
import json
import logging
import os
from pathlib import Path

before_handlers = len(logging.getLogger().handlers)
import mcp_crm.drivers.mcp_server as server
after_handlers = len(logging.getLogger().handlers)
payload = {
    'module': server.mcp.name,
    'db_exists': Path(os.environ['MCP_DB_PATH']).exists(),
    'faiss_exists': Path(os.environ['MCP_FAISS_PATH']).exists(),
    'handlers_before': before_handlers,
    'handlers_after': after_handlers,
}
print(json.dumps(payload))
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(completed.stdout.strip())

    assert payload == {
        "module": "mcp-crm",
        "db_exists": False,
        "faiss_exists": False,
        "handlers_before": 0,
        "handlers_after": 0,
    }
