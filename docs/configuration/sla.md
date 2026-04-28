# SLA Timeouts

**File:** `app/config/sla.py`

Per-model timeout budgets. When a model call exceeds its budget, the executor raises `ExecutionTimeoutError` and the job is marked `failed`.

---

## Configuration

```python
# app/config/sla.py
SLA_TIMEOUTS: dict[str, float | None] = {
    "heavy_model:v1": 30.0,   # 30 seconds
    "fast_model:v1":   2.0,   # 2 seconds
}

DEFAULT_TIMEOUT_S: float | None = None  # None = no global timeout
```

Keys are `"model:version"` strings. `DEFAULT_TIMEOUT_S` applies to any model not listed.

---

## Priority

Timeouts are resolved in this order:

1. **Explicit `timeout_s`** passed by the caller (e.g. from a future per-request header)
2. **Per-model SLA** from `SLA_TIMEOUTS`
3. **Global default** `DEFAULT_TIMEOUT_S`
4. **`None`** — no timeout enforced

---

## Behaviour on timeout

- The executor raises `ExecutionTimeoutError`.
- `PredictionService` catches it, increments `inference_errors_total{error_type="timeout"}`, marks the job `failed`, and raises `InferenceExecutionError` → HTTP `500`.
- The OTel span records the exception.
