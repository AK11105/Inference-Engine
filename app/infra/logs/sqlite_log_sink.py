"""SQLite-backed persistent log sink.

Mirrors app/infra/jobs/sqlite_job_store.py's connection/migration style.
Writes happen only on the QueueListener's dedicated thread (see build_sink),
so — unlike SQLiteJobStore — no lock is needed: there is a single writer.
"""
import json
import logging
import queue
import sqlite3
from datetime import datetime, timezone
from logging.handlers import QueueHandler, QueueListener
from typing import Any, Optional

_CURRENT_SCHEMA_VERSION = 1

_DDL = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL,
    event_type TEXT NOT NULL,
    request_id TEXT,
    deployment_id TEXT,
    job_id TEXT,
    model_id TEXT,
    tenant_id TEXT,
    message TEXT,
    payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_event_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_request_id ON events(request_id);
CREATE INDEX IF NOT EXISTS idx_events_job_id ON events(job_id);
CREATE INDEX IF NOT EXISTS idx_events_deployment_id ON events(deployment_id);
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);
"""

_KNOWN_FIELDS = {"event_type", "request_id", "deployment_id", "job_id", "model_id", "tenant_id"}


def _make_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(_DDL)
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    stored = row["version"] if row else 0
    if stored < _CURRENT_SCHEMA_VERSION:
        conn.execute("DELETE FROM schema_version")
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (_CURRENT_SCHEMA_VERSION,))
        conn.commit()


class SQLiteLogHandler(logging.Handler):
    """Only ever invoked from a QueueListener thread — single writer, no lock."""

    def __init__(self, db_path: str):
        super().__init__()
        self._conn = _make_conn(db_path)
        _migrate(self._conn)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            extra = getattr(record, "extra", {}) or {}
            payload = {k: v for k, v in extra.items() if k not in _KNOWN_FIELDS}
            self._conn.execute(
                "INSERT INTO events "
                "(timestamp, level, event_type, request_id, deployment_id, job_id, model_id, "
                " tenant_id, message, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    record.levelname,
                    extra.get("event_type", record.getMessage()),
                    extra.get("request_id"),
                    extra.get("deployment_id"),
                    extra.get("job_id"),
                    extra.get("model_id"),
                    extra.get("tenant_id"),
                    record.getMessage(),
                    json.dumps(payload) if payload else None,
                ),
            )
            self._conn.commit()
        except Exception:
            # Fault tolerance: a broken log sink must never interrupt model serving.
            pass


def build_sink(db_path: str) -> QueueListener:
    """Wire QueueHandler -> queue.Queue -> QueueListener(SQLiteLogHandler).

    Returned listener must be `.start()`ed by the caller and `.stop()`ed on
    shutdown so buffered events flush before the process exits.
    """
    log_queue: queue.Queue = queue.Queue(-1)
    queue_handler = QueueHandler(log_queue)
    sqlite_handler = SQLiteLogHandler(db_path)
    listener = QueueListener(log_queue, sqlite_handler, respect_handler_level=True)
    listener.queue_handler = queue_handler  # stash for setup_logging to attach
    return listener


def query_events(
    db_path: str,
    *,
    event_type: Optional[str] = None,
    request_id: Optional[str] = None,
    job_id: Optional[str] = None,
    deployment_id: Optional[str] = None,
    model_id: Optional[str] = None,
    since: Optional[str] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    conn = _make_conn(db_path)
    _migrate(conn)
    clauses, params = [], []
    for column, value in (
        ("event_type", event_type),
        ("request_id", request_id),
        ("job_id", job_id),
        ("deployment_id", deployment_id),
        ("model_id", model_id),
    ):
        if value is not None:
            clauses.append(f"{column} = ?")
            params.append(value)
    if since is not None:
        clauses.append("timestamp >= ?")
        params.append(since)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM events {where} ORDER BY id DESC LIMIT ?", (*params, limit)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]
