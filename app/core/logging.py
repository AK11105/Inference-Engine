import logging
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from app.core.context import ContextFilter


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_record: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra"):
            log_record.update(record.extra)
        return json.dumps(log_record)


def setup_logging() -> Optional[Any]:
    """Configure stdout JSON logging plus, outside production, a durable SQLite
    sink. Returns the sink's QueueListener (or None) — stop it on shutdown so
    buffered events flush before the process exits."""
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers = [handler]
    root.addFilter(ContextFilter())

    listener = None
    if os.environ.get("ENV") != "production":
        from app.infra.logs.sqlite_log_sink import build_sink

        db_path = os.environ.get("LOG_DB_PATH", "app/instance/logs.db")
        listener = build_sink(db_path)
        root.addHandler(listener.queue_handler)
        listener.start()

    return listener
