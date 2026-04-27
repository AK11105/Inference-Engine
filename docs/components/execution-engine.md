# Execution Engine

**Files:** `app/execution/`

The execution layer wraps inference callables in a thread pool with timeout tracking and Prometheus metrics. It is injected into the service layer via `ExecutionPolicy`.

---

## BaseExecutor

```python
# app/execution/base.py
class BaseExecutor(ABC):
    def submit(self, fn, *args, timeout_s=None) -> Any: ...       # blocking
    def submit_batch(self, fn, timeout_s=None) -> Any: ...        # default: delegates to submit()
    def submit_background(self, fn, *args) -> None: ...           # fire-and-forget
```

All executors implement this interface. `submit()` blocks until the result is ready or `timeout_s` elapses. `submit_background()` is used for async jobs — it returns immediately.

---

## InferenceExecutor (default)

```python
# app/execution/executor.py
executor = InferenceExecutor(device="cpu", max_workers=8)
```

`ThreadPoolExecutor`-backed. Works for any Python model. Raises `ExecutionTimeoutError` on timeout.

Metrics updated on every call:
- `executor_inflight{device}` — incremented on entry, decremented on exit
- `executor_timeouts_total{device}` — incremented on timeout

Two instances are created by default in `deps.py`: `cpu` (8 workers) and `gpu` (2 workers).

---

## OnnxExecutor

```python
# app/execution/onnx_executor.py
from app.execution.onnx_executor import OnnxExecutor
executor = OnnxExecutor(max_workers=4)
```

Thread-pool executor sized for ONNX Runtime workloads. ONNX Runtime releases the GIL during inference, so a thread pool gives real CPU parallelism.

**Requires:** `pip install onnxruntime`

Raises `RuntimeError` at construction time if `onnxruntime` is not installed.

---

## TritonExecutor

```python
# app/execution/triton_executor.py
from app.execution.triton_executor import TritonExecutor
executor = TritonExecutor(url="triton-host:8001", max_workers=8)
```

Wraps a remote Triton Inference Server gRPC call in a thread pool. Pre/postprocessing still runs locally; only the model call goes remote.

**Requires:** `pip install tritonclient[grpc]`

Raises `RuntimeError` at construction time if `tritonclient` is not installed.

---

## ExecutionPolicy

```python
# app/execution/execution_policy.py
policy = ExecutionPolicy(
    executors={"cpu": cpu_executor, "gpu": gpu_executor},
    policy={"echo:v1": "gpu", "echo:v2": "cpu"},
    default="cpu",
)
executor = policy.resolve("echo", "v1")  # → gpu_executor
```

Maps `model:version` keys to executor instances. Falls back to `default` for any key not listed. Raises `RuntimeError` if the resolved executor name is not in `executors`.

Configured via `app/config/execution.py`. See [Execution Configuration](../configuration/execution.md).

---

## Writing a custom executor

```python
from app.execution.base import BaseExecutor

class MyExecutor(BaseExecutor):
    def submit(self, fn, *args, timeout_s=None):
        return fn(*args)

    def submit_background(self, fn, *args):
        threading.Thread(target=fn, args=args, daemon=True).start()
```

Register it in `deps.py` under a name, then reference that name in `EXECUTION_POLICY`.
