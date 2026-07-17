import json
import logging

from app.core import context
from app.core.context import ContextFilter
from app.core.events import log_event
from app.core.logging import JSONFormatter
from app.infra.logs.sqlite_log_sink import SQLiteLogHandler, query_events


def _events_logger(handler):
    logger = logging.getLogger("inference_engine.events")
    logger.handlers = [handler]
    logger.filters = []
    logger.propagate = False
    logger.setLevel(logging.INFO)
    return logger


def test_json_formatter_includes_extra_fields(capsys):
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    _events_logger(handler)

    log_event("PredictionCompleted", request_id="req-1", job_id="job-1")

    record = json.loads(capsys.readouterr().err.strip())
    assert record["request_id"] == "req-1"
    assert record["job_id"] == "job-1"
    assert record["event_type"] == "PredictionCompleted"


def test_context_filter_propagates_bound_request_id(capsys):
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logger = _events_logger(handler)
    logger.addFilter(ContextFilter())

    with context.bind(request_id="req-ambient"):
        log_event("PredictionCompleted", job_id="job-2")
    record = json.loads(capsys.readouterr().err.strip())
    assert record["request_id"] == "req-ambient"
    assert record["job_id"] == "job-2"

    # Outside the `with` block, the var must not leak into later records.
    log_event("PredictionCompleted", job_id="job-3")
    record2 = json.loads(capsys.readouterr().err.strip())
    assert "request_id" not in record2


def test_sqlite_log_handler_swallows_write_failures():
    handler = SQLiteLogHandler(":memory:")
    handler._conn.close()  # force emit() to fail

    record = logging.LogRecord("x", logging.INFO, __file__, 1, "boom", (), None)
    handler.emit(record)  # must not raise


def test_query_events_round_trips_inserted_event(tmp_path):
    db_path = str(tmp_path / "logs.db")
    handler = SQLiteLogHandler(db_path)
    record = logging.LogRecord(
        "inference_engine.events", logging.INFO, __file__, 1, "PredictionCompleted", (), None,
    )
    record.extra = {"event_type": "PredictionCompleted", "request_id": "req-9", "job_id": "job-9"}
    handler.emit(record)

    results = query_events(db_path, event_type="PredictionCompleted")
    assert len(results) == 1
    assert results[0]["request_id"] == "req-9"
    assert results[0]["job_id"] == "job-9"

    assert query_events(db_path, request_id="does-not-exist") == []
