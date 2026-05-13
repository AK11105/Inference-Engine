# Execution Backends

**Files:** `app/execution/`

The execution layer wraps inference callables in a thread pool with timeout tracking and Prometheus metrics. It is injected into the service layer via `ExecutionPolicy`.

---

## BaseExecutor

```python
class BaseExecutor(ABC):
    def submit(self, fn, *args, timeout_s=None) -> Any: ...       # blocking
    def submit_batch(self, fn, timeout_s=None) -> Any: ...
    def submit_background(self, fn, *args) -> None: ...           # fire-and-forget
```

`submit()` blocks until the result is ready or `timeout_s` elapses. `submit_background()` is used for async jobs.

---

## InferenceExecutor (default)

`ThreadPoolExecutor`-backed. Works for any Python model. Raises `ExecutionTimeoutError` on timeout.

```python
executor = InferenceExecutor(device="cpu", max_workers=8)
```

Two instances are created by default: `cpu` (8 workers) and `gpu` (2 workers).

---

## OnnxExecutor

Thread-pool executor for ONNX Runtime workloads. ONNX Runtime releases the GIL during inference, so a thread pool gives real CPU parallelism.

```python
from app.execution.onnx_executor import OnnxExecutor
executor = OnnxExecutor(max_workers=4)
```

**Requires:** `pip install onnxruntime`

---

## TritonExecutor

Wraps a remote Triton Inference Server gRPC call in a thread pool. Pre/postprocessing still runs locally; only the model call goes remote.

```python
from app.execution.triton_executor import TritonExecutor
executor = TritonExecutor(url="triton-host:8001", max_workers=8)
```

**Requires:** `pip install tritonclient[grpc]`

---

## ExecutionPolicy

![Execution policy resolution diagram](../assets/execution-policy-resolution-light.png#only-light)
![Execution policy resolution diagram](../assets/execution-policy-resolution-dark.png#only-dark)

Maps `model:version` keys to executor instances. Falls back to `default` for any key not listed.

```python
policy = ExecutionPolicy(
    executors={"cpu": cpu_executor, "gpu": gpu_executor},
    policy={"echo:v1": "gpu", "echo:v2": "cpu"},
    default="cpu",
)
executor = policy.resolve("echo", "v1")  # → gpu_executor
```

See [Execution Configuration](../configuration/execution.md).

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
