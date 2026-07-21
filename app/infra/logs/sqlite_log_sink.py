"""SQLite-backed persistent log sink.

Mirrors app/infra/jobs/sqlite_job_store.py's connection/migration style.
Writes happen only on the QueueListener's dedicated thread (see build_sink),
so — unlike SQLiteJobStore — no lock is needed: there is a single writer.
"""
import json
import logging
import os
import queue
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from logging.handlers import QueueHandler, QueueListener
from typing import Any, Optional

DEFAULT_DB_PATH = "logs/events.db"

_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"]
_LEVEL_RANK_SQL = (
    "CASE level WHEN 'DEBUG' THEN 0 WHEN 'INFO' THEN 1 "
    "WHEN 'WARNING' THEN 2 WHEN 'ERROR' THEN 3 ELSE 1 END"
)
_SINCE_RE = re.compile(r"^(\d+)([smhd])$")
_SINCE_UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}


def _resolve_since(since: str) -> str:
    """Turn a relative window ("5m", "1h", "24h", "7d") into an ISO cutoff.

    Falls back to treating `since` as an already-absolute ISO timestamp.
    """
    match = _SINCE_RE.match(since.strip())
    if not match:
        return since
    amount, unit = match.groups()
    delta = timedelta(**{_SINCE_UNITS[unit]: int(amount)})
    return (datetime.now(timezone.utc) - delta).isoformat()

_CURRENT_SCHEMA_VERSION = 2

_DDL = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL,
    event TEXT NOT NULL,
    component TEXT,
    request_id TEXT,
    deployment_id TEXT,
    job_id TEXT,
    model_id TEXT,
    tenant_id TEXT,
    message TEXT,
    payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_level ON events(level);
CREATE INDEX IF NOT EXISTS idx_events_event ON events(event);
CREATE INDEX IF NOT EXISTS idx_events_component ON events(component);
CREATE INDEX IF NOT EXISTS idx_events_request_id ON events(request_id);
CREATE INDEX IF NOT EXISTS idx_events_job_id ON events(job_id);
CREATE INDEX IF NOT EXISTS idx_events_deployment_id ON events(deployment_id);
CREATE INDEX IF NOT EXISTS idx_events_model_id ON events(model_id);
"""

_SCHEMA_VERSION_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);
"""

_KNOWN_FIELDS = {
    "event", "component", "request_id", "deployment_id", "job_id", "model_id", "tenant_id",
}


def _make_conn(db_path: str) -> sqlite3.Connection:
    if db_path != ":memory:":
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA_VERSION_DDL)
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    stored = row["version"] if row else 0
    if stored < _CURRENT_SCHEMA_VERSION:
        # Drop before (re)creating so a stale (pre-rename) column shape
        # can't collide with the current DDL's indexes.
        conn.executescript("DROP TABLE IF EXISTS events;")
        conn.execute("DELETE FROM schema_version")
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (_CURRENT_SCHEMA_VERSION,))
        conn.commit()
    conn.executescript(_DDL)


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
                "(timestamp, level, event, component, request_id, deployment_id, job_id, "
                " model_id, tenant_id, message, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    record.levelname,
                    extra.get("event", record.getMessage()),
                    extra.get("component"),
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
        except Exception as exc:
            # Fault tolerance: a broken log sink must never interrupt model serving.
            print(f"WARNING: SQLite log write failed: {exc}")


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


def purge_old_events(db_path: str, retention_days: int = 7, *, older_than: Optional[str] = None) -> int:
    """Delete events older than `retention_days` (or the relative `older_than` window, e.g. "7d")."""
    conn = _make_conn(db_path)
    _migrate(conn)
    cutoff = (
        _resolve_since(older_than)
        if older_than is not None
        else (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    )
    cur = conn.execute("DELETE FROM events WHERE timestamp < ?", (cutoff,))
    conn.commit()
    conn.close()
    return cur.rowcount


def get_log_stats(db_path: str) -> dict[str, Any]:
    conn = _make_conn(db_path)
    _migrate(conn)
    count = conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"]
    oldest = conn.execute("SELECT MIN(timestamp) AS t FROM events").fetchone()["t"]
    conn.close()
    size_bytes = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    return {"count": count, "oldest": oldest, "size_bytes": size_bytes}


def query_events(
    db_path: str,
    *,
    event: Optional[str] = None,
    component: Optional[str] = None,
    request_id: Optional[str] = None,
    job_id: Optional[str] = None,
    deployment_id: Optional[str] = None,
    model_id: Optional[str] = None,
    level: Optional[str] = None,
    since: Optional[str] = None,
    after_id: Optional[int] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    conn = _make_conn(db_path)
    _migrate(conn)
    clauses, params = [], []
    if event is not None:
        clauses.append("event LIKE ?")
        params.append(f"{event}%")
    for column, value in (
        ("component", component),
        ("request_id", request_id),
        ("job_id", job_id),
        ("deployment_id", deployment_id),
        ("model_id", model_id),
    ):
        if value is not None:
            clauses.append(f"{column} = ?")
            params.append(value)
    if level is not None:
        clauses.append(f"({_LEVEL_RANK_SQL}) >= ?")
        params.append(_LEVELS.index(level.upper()))
    if since is not None:
        clauses.append("timestamp >= ?")
        params.append(_resolve_since(since))
    if after_id is not None:
        clauses.append("id > ?")
        params.append(after_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    order = "ASC" if after_id is not None else "DESC"
    rows = conn.execute(
        f"SELECT * FROM events {where} ORDER BY id {order} LIMIT ?", (*params, limit)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]
