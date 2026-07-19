import json
import logging

import pytest

from app.core import context
from app.core.context import ContextFilter
from app.core.logging import JSONFormatter, get_logger, setup_logging
from app.infra.logs.sqlite_log_sink import SQLiteLogHandler, purge_old_events, query_events


@pytest.fixture(autouse=True)
def _reset_correlation_context():
    token = context.correlation_ctx.set({})
    yield
    context.correlation_ctx.reset(token)


@pytest.fixture
def _restore_root_logger():
    root = logging.getLogger()
    handlers, level, filters = list(root.handlers), root.level, list(root.filters)
    yield
    root.handlers = handlers
    root.level = level
    root.filters = filters


def _wired_logger(handler):
    raw = logging.getLogger("test_logging_core")
    raw.handlers = [handler]
    raw.filters = []
    raw.propagate = False
    raw.setLevel(logging.INFO)
    return get_logger("test_logging_core")


def test_json_formatter_includes_extra_fields(capsys):
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logger = _wired_logger(handler)

    logger.info(event="PredictionCompleted", request_id="req-1", job_id="job-1")

    record = json.loads(capsys.readouterr().err.strip())
    assert record["request_id"] == "req-1"
    assert record["job_id"] == "job-1"
    assert record["event"] == "PredictionCompleted"


def test_correlation_context_propagates_and_merges(capsys):
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    raw = logging.getLogger("test_logging_core")
    raw.handlers = [handler]
    raw.filters = []
    raw.propagate = False
    raw.setLevel(logging.INFO)
    raw.addFilter(ContextFilter())
    logger = get_logger("test_logging_core")

    context.set_correlation_context(request_id="req-ambient")
    context.set_correlation_context(job_id="job-2")  # must not erase request_id
    logger.info(event="PredictionCompleted")

    record = json.loads(capsys.readouterr().err.strip())
    assert record["request_id"] == "req-ambient"
    assert record["job_id"] == "job-2"


def test_sqlite_log_handler_warns_to_stdout_on_write_failure(capsys):
    handler = SQLiteLogHandler(":memory:")
    handler._conn.close()  # force emit() to fail

    record = logging.LogRecord("x", logging.INFO, __file__, 1, "boom", (), None)
    handler.emit(record)  # must not raise

    out = capsys.readouterr().out
    assert "WARNING" in out and "SQLite log write failed" in out


def test_query_events_round_trips_inserted_event(tmp_path):
    db_path = str(tmp_path / "logs.db")
    handler = SQLiteLogHandler(db_path)
    record = logging.LogRecord(
        "test_logging_core", logging.INFO, __file__, 1, "PredictionCompleted", (), None,
    )
    record.extra = {
        "event": "PredictionCompleted", "component": "PredictionService",
        "request_id": "req-9", "job_id": "job-9",
    }
    handler.emit(record)

    results = query_events(db_path, event="PredictionCompleted")
    assert len(results) == 1
    assert results[0]["component"] == "PredictionService"
    assert results[0]["request_id"] == "req-9"
    assert results[0]["job_id"] == "job-9"

    assert query_events(db_path, request_id="does-not-exist") == []
    assert query_events(db_path, component="DeploymentCLI") == []


def test_purge_old_events_deletes_only_rows_past_retention(tmp_path):
    db_path = str(tmp_path / "logs.db")
    handler = SQLiteLogHandler(db_path)  # creates the schema
    handler._conn.execute(
        "INSERT INTO events (timestamp, level, event) VALUES "
        "('2000-01-01T00:00:00+00:00', 'INFO', 'OldEvent'), "
        "('2999-01-01T00:00:00+00:00', 'INFO', 'FutureEvent')"
    )
    handler._conn.commit()

    deleted = purge_old_events(db_path, retention_days=7)
    assert deleted == 1

    remaining = query_events(db_path, limit=10)
    assert [r["event"] for r in remaining] == ["FutureEvent"]


def test_log_level_env_var_controls_verbosity(monkeypatch, tmp_path, _restore_root_logger):
    monkeypatch.setenv("LOG_DB_PATH", ":memory:")
    monkeypatch.setenv("LOG_ERROR_FILE", str(tmp_path / "error.log"))
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    listener = setup_logging()
    try:
        assert logging.getLogger().level == logging.DEBUG
    finally:
        if listener is not None:
            listener.stop()

    monkeypatch.setenv("LOG_LEVEL", "NOT_A_LEVEL")
    listener = setup_logging()
    try:
        assert logging.getLogger().level == logging.INFO
    finally:
        if listener is not None:
            listener.stop()


def test_error_file_handler_captures_error_level_only(monkeypatch, tmp_path, _restore_root_logger):
    error_log = tmp_path / "error.log"
    monkeypatch.setenv("LOG_DB_PATH", ":memory:")
    monkeypatch.setenv("LOG_ERROR_FILE", str(error_log))
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    listener = setup_logging()
    try:
        logger = get_logger("test_logging_core_error_file")
        logger.info(event="PredictionCompleted")
        logger.error(event="PredictionFailed")
    finally:
        if listener is not None:
            listener.stop()

    contents = error_log.read_text()
    lines = [json.loads(line) for line in contents.strip().splitlines()]
    assert len(lines) == 1
    assert lines[0]["event"] == "PredictionFailed"
