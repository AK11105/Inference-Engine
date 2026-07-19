"""Correlation-ID propagation via contextvars.

Lets any log call pick up request_id/deployment_id/job_id/model_id without
callers threading them through every function signature explicitly.
"""
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional

request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
deployment_id_var: ContextVar[Optional[str]] = ContextVar("deployment_id", default=None)
job_id_var: ContextVar[Optional[str]] = ContextVar("job_id", default=None)
model_id_var: ContextVar[Optional[str]] = ContextVar("model_id", default=None)

_VARS = {
    "request_id": request_id_var,
    "deployment_id": deployment_id_var,
    "job_id": job_id_var,
    "model_id": model_id_var,
}


@contextmanager
def bind(**fields):
    """Set correlation vars for the duration of a `with` block."""
    tokens = {name: var.set(fields[name]) for name, var in _VARS.items() if name in fields}
    try:
        yield
    finally:
        for name, token in tokens.items():
            _VARS[name].reset(token)


class ContextFilter(logging.Filter):
    """Merges bound correlation vars into record.extra (explicit extra wins)."""

    def filter(self, record: logging.LogRecord) -> bool:
        ambient = {name: var.get() for name, var in _VARS.items() if var.get() is not None}
        if ambient:
            record.extra = {**ambient, **getattr(record, "extra", {})}
        return True
