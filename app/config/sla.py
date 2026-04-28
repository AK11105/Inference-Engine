"""
Per-model SLA timeout budgets (seconds).

Keys are "model:version" strings.  DEFAULT_TIMEOUT_S is used when no
specific entry exists.  Set to None to disable timeouts entirely.

Example:
    SLA_TIMEOUTS = {
        "echo:v1": 5.0,
        "heavy_model:v1": 30.0,
    }
    DEFAULT_TIMEOUT_S = 10.0
"""
from typing import Optional

SLA_TIMEOUTS: dict[str, Optional[float]] = {
    # "echo:v1": 5.0,
}

DEFAULT_TIMEOUT_S: Optional[float] = None  # no global default; per-request timeout wins
