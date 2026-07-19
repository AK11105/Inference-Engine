import logging
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from app.core.context import ContextFilter

_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


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


class StructuredLogger:
    """logger.info(event="PredictionCompleted", component="...", **fields) —
    lifecycle events over free-form messages. Never raises into callers."""

    def __init__(self, logger: logging.Logger):
        self._logger = logger

    def _emit(self, level: int, event: str, **fields) -> None:
        try:
            self._logger.log(level, event, extra={"extra": {"event": event, **fields}})
        except Exception:
            pass

    def debug(self, event: str, **fields) -> None:
        self._emit(logging.DEBUG, event, **fields)

    def info(self, event: str, **fields) -> None:
        self._emit(logging.INFO, event, **fields)

    def warning(self, event: str, **fields) -> None:
        self._emit(logging.WARNING, event, **fields)

    def error(self, event: str, **fields) -> None:
        self._emit(logging.ERROR, event, **fields)

    def critical(self, event: str, **fields) -> None:
        self._emit(logging.CRITICAL, event, **fields)


def get_logger(name: str) -> StructuredLogger:
    return StructuredLogger(logging.getLogger(name))


def _resolve_log_level(root: logging.Logger) -> int:
    raw = os.environ.get("LOG_LEVEL", "INFO").strip().upper()
    if raw not in _VALID_LEVELS:
        root.warning("invalid LOG_LEVEL=%r, falling back to INFO", raw)
        raw = "INFO"
    return getattr(logging, raw)


def setup_logging() -> Optional[Any]:
    """Configure stdout JSON logging plus, outside production, a durable SQLite
    sink, plus an always-on ERROR+ file. Returns the sink's QueueListener (or
    None) — stop it on shutdown so buffered events flush before exit."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.addFilter(ContextFilter())
    root.setLevel(_resolve_log_level(root))

    error_log_path = os.environ.get("LOG_ERROR_FILE", "logs/error.log")
    try:
        parent = os.path.dirname(error_log_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        error_handler = logging.FileHandler(error_log_path)
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(JSONFormatter())
        root.addHandler(error_handler)
    except Exception as exc:
        root.warning("failed to attach error log file at %s: %s", error_log_path, exc)

    listener = None
    if os.environ.get("ENV") != "production":
        from app.infra.logs.sqlite_log_sink import DEFAULT_DB_PATH, build_sink, purge_old_events

        db_path = os.environ.get("LOG_DB_PATH", DEFAULT_DB_PATH)
        try:
            listener = build_sink(db_path)
            root.addHandler(listener.queue_handler)
            listener.start()
            retention_days = int(os.environ.get("LOG_RETENTION_DAYS", "7"))
            purge_old_events(db_path, retention_days=retention_days)
        except Exception as exc:
            # Fault tolerance: an unavailable log sink must never block startup.
            listener = None
            root.warning("failed to attach SQLite log sink at %s: %s", db_path, exc)

    return listener
