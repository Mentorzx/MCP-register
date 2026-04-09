from __future__ import annotations

import shutil

from mcp_crm.slices.users.infrastructure import config as config_module


CONFIG_TEXT = """app:
  name: mcp-crm
  version: 0.1.0
  instructions: test

runtime:
  data_dir: data/runtime
  db_filename: users.db
  sqlite_timeout_seconds: 30

embedding:
  provider: deterministic
  model: deterministic

search:
  default_top_k: 5
  max_top_k: 100

pagination:
  default_limit: 20
  max_limit: 100

testing:
  deterministic_embedding_dimensions: 16
  docker_image: mcp-crm:latest

logging:
  default_format: json

llm:
  provider: stub
  model: gpt-4.1-mini
  base_url: https://api.openai.com/v1
  timeout_seconds: 30
  system_prompt: stub
"""


def test_get_settings_falls_back_to_tmp_runtime_when_default_data_dir_is_not_writable(
    tmp_path,
    monkeypatch,
):
    repo_root = tmp_path / "repo"
    (repo_root / "config").mkdir(parents=True)
    (repo_root / "config" / "config.yaml").write_text(CONFIG_TEXT, encoding="utf-8")

    locked_runtime = repo_root / "data" / "runtime"
    locked_runtime.mkdir(parents=True)

    monkeypatch.setattr(config_module, "_root_dir", lambda: repo_root)

    original_is_writable_directory = config_module._is_writable_directory
    original_is_writable_path = config_module._is_writable_path

    def fake_is_writable_directory(path):
        if path == locked_runtime:
            return False
        return original_is_writable_directory(path)

    def fake_is_writable_path(path):
        if path.parent == locked_runtime:
            return False
        return original_is_writable_path(path)

    monkeypatch.setattr(
        config_module,
        "_is_writable_directory",
        fake_is_writable_directory,
    )
    monkeypatch.setattr(
        config_module,
        "_is_writable_path",
        fake_is_writable_path,
    )

    for key in (
        "MCP_DB_PATH",
        "MCP_IMPORT_DIR",
        "MCP_IMPORT_CACHE_DIR",
        "MCP_IMPORT_SOURCE_PATH",
    ):
        monkeypatch.delenv(key, raising=False)

    config_module.get_project_config.cache_clear()
    try:
        settings = config_module.get_settings()
    finally:
        config_module.get_project_config.cache_clear()

    assert settings.data_dir == repo_root / ".tmp" / "runtime"
    assert settings.db_path == repo_root / ".tmp" / "runtime" / "users.db"
    assert settings.json_import_dir == repo_root / ".tmp" / "runtime" / "import"
    assert (
        settings.json_import_cache_dir
        == repo_root / ".tmp" / "runtime" / "import-cache"
    )


def test_get_settings_falls_back_to_system_tmp_when_repo_tmp_is_not_writable(
    tmp_path,
    monkeypatch,
):
    repo_root = tmp_path / "repo"
    (repo_root / "config").mkdir(parents=True)
    (repo_root / "config" / "config.yaml").write_text(CONFIG_TEXT, encoding="utf-8")

    locked_runtime = repo_root / "data" / "runtime"
    locked_runtime.mkdir(parents=True)

    fallback_in_repo, fallback_in_system_tmp = (
        config_module._runtime_fallback_candidates(repo_root)
    )

    monkeypatch.setattr(config_module, "_root_dir", lambda: repo_root)

    original_is_writable_directory = config_module._is_writable_directory
    original_is_writable_path = config_module._is_writable_path

    def fake_is_writable_directory(path):
        if path in {locked_runtime, fallback_in_repo}:
            return False
        return original_is_writable_directory(path)

    def fake_is_writable_path(path):
        if path.parent in {locked_runtime, fallback_in_repo}:
            return False
        return original_is_writable_path(path)

    monkeypatch.setattr(
        config_module,
        "_is_writable_directory",
        fake_is_writable_directory,
    )
    monkeypatch.setattr(
        config_module,
        "_is_writable_path",
        fake_is_writable_path,
    )

    for key in (
        "MCP_DB_PATH",
        "MCP_IMPORT_DIR",
        "MCP_IMPORT_CACHE_DIR",
        "MCP_IMPORT_SOURCE_PATH",
    ):
        monkeypatch.delenv(key, raising=False)

    config_module.get_project_config.cache_clear()
    try:
        settings = config_module.get_settings()
    finally:
        config_module.get_project_config.cache_clear()

    assert settings.data_dir == fallback_in_system_tmp
    assert settings.db_path == fallback_in_system_tmp / "users.db"
    assert settings.json_import_dir == fallback_in_system_tmp / "import"
    assert settings.json_import_cache_dir == fallback_in_system_tmp / "import-cache"

    shutil.rmtree(fallback_in_system_tmp.parent.parent, ignore_errors=True)
