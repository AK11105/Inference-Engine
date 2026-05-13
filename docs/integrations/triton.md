# Triton Inference Server

Use `TritonExecutor` to offload model inference to a remote Triton Inference Server while keeping pre/postprocessing local.

---

## Install

```bash
pip install tritonclient[grpc]
```

---

## Configure

```python
# app/adapters/http/deps.py
from app.execution.triton_executor import TritonExecutor

@lru_cache
def get_triton_executor():
    return TritonExecutor(url="triton-host:8001", max_workers=8)
```

Register it in `ExecutionPolicy`:

```python
@lru_cache
def get_execution_policy() -> ExecutionPolicy:
    return ExecutionPolicy(
        executors={
            "cpu": get_cpu_executor(),
            "triton": get_triton_executor(),
        },
        policy={"my_model:v1": "triton"},
        default="cpu",
    )
```

---

## How it works

Pre/postprocessing runs locally in the inference engine. Only the `model.predict()` call is sent to Triton via gRPC. The pipeline structure is unchanged.

---

## Requirements

- Triton Inference Server running and accessible at the configured URL
- Model loaded in Triton's model repository
- `tritonclient[grpc]` installed in the inference engine environment
