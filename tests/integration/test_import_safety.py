import logging
import sys


def test_import_does_not_create_runtime_files(tmp_path, monkeypatch):
    """Importing the MCP driver should not trigger file creation or logging setup."""
    monkeypatch.setenv("MCP_DB_PATH", str(tmp_path / "nope.db"))

    # clear cached modules so we get a fresh import
    mods_to_clear = [k for k in sys.modules if k.startswith("mcp_crm")]
    for m in mods_to_clear:
        del sys.modules[m]

    root_logger = logging.getLogger()
    handler_count_before = len(root_logger.handlers)
    import mcp_crm.drivers.mcp_server  # noqa: F401

    assert not (tmp_path / "nope.db").exists()
    assert len(root_logger.handlers) == handler_count_before
