"""Lifecycle event logging — structured events over free-form messages."""
import logging

_events_logger = logging.getLogger("inference_engine.events")


def log_event(event_type: str, level: int = logging.INFO, **fields) -> None:
    """Emit a structured lifecycle event (e.g. PredictionCompleted, DeploymentStarted)."""
    _events_logger.log(level, event_type, extra={"extra": {"event_type": event_type, **fields}})
