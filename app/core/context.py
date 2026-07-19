"""Correlation-ID propagation via a single contextvars dict.

Lets any log call pick up request_id/deployment_id/job_id/model_id without
callers threading them through every function signature explicitly.
"""
import logging
from contextvars import ContextVar
from typing import Any, Dict

correlation_ctx: ContextVar[Dict[str, Any]] = ContextVar("correlation_ctx", default={})


def set_correlation_context(**fields) -> None:
    """Merge fields into the current asyncio Task's correlation context.

    Set once (request_id in middleware, job_id/deployment_id where they
    become known) — every log call downstream in the same task picks it up
    automatically. Each ASGI request runs in its own Task (a fresh
    contextvars copy), so this can't leak into other concurrent requests;
    no explicit reset is needed.
    """
    current = correlation_ctx.get()
    updates = {k: v for k, v in fields.items() if v is not None}
    correlation_ctx.set({**current, **updates})


class ContextFilter(logging.Filter):
    """Merges the current correlation context into record.extra (explicit extra wins)."""

    def filter(self, record: logging.LogRecord) -> bool:
        ambient = correlation_ctx.get()
        if ambient:
            record.extra = {**ambient, **getattr(record, "extra", {})}
        return True
