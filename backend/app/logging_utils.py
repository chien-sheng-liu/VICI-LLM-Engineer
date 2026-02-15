from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict


def configure_json_logging() -> None:
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    formatter = _JsonFormatter()
    handler.setFormatter(formatter)
    logger.handlers = [handler]


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        base: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        args = record.args
        # allow structured args to merge if provided as single dict arg
        if isinstance(args, dict):
            base.update(args)
        elif isinstance(args, tuple) and len(args) == 1 and isinstance(args[0], dict):
            base.update(args[0])
        return json.dumps(base, ensure_ascii=False)


def log_event(**fields: Any) -> None:
    logging.getLogger("gateway").info("event", fields)
