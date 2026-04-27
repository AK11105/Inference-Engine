# Execution Configuration

**File:** `app/config/execution.py`

Maps `model:version` keys to executor names. Falls back to `DEFAULT_EXECUTOR` for any key not listed.

```python
EXECUTION_POLICY = {
    "echo:v1": "gpu",
    "echo:v2": "cpu",
}

DEFAULT_EXECUTOR = "cpu"
```

---

## Available executors

| Name | Class | Workers |
|---|---|---|
| `cpu` | `InferenceExecutor(device="cpu")` | 8 |
| `gpu` | `InferenceExecutor(device="gpu")` | 2 |

---

## Adding a custom executor

Register it in `app/adapters/http/deps.py`:

```python
@lru_cache
def get_onnx_executor():
    from app.execution.onnx_executor import OnnxExecutor
    return OnnxExecutor(max_workers=4)

@lru_cache
def get_execution_policy() -> ExecutionPolicy:
    return ExecutionPolicy(
        executors={
            "cpu": get_cpu_executor(),
            "gpu": get_gpu_executor(),
            "onnx": get_onnx_executor(),
        },
        policy=EXECUTION_POLICY,
        default=DEFAULT_EXECUTOR,
    )
```

Then reference `"onnx"` in `EXECUTION_POLICY`.

See [Execution Engine component](../components/execution-engine.md) for executor details.
