from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime

from mcp_crm.slices.users.infrastructure.config import get_project_config

_BUILTIN_FIELDS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extras = {
            k: v
            for k, v in record.__dict__.items()
            if k not in _BUILTIN_FIELDS and not k.startswith("_")
        }
        if extras:
            payload["ctx"] = extras
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True, default=str)


def configure_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return

    cfg = get_project_config()
    handler = logging.StreamHandler()
    fmt = os.getenv("MCP_LOG_FORMAT", cfg.logging.default_format).lower()
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        )
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
