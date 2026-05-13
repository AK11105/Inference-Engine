# ONNX Runtime

Use `OnnxExecutor` for models exported to the ONNX format. ONNX Runtime releases the GIL during inference, so a thread pool gives real CPU parallelism.

---

## Install

```bash
pip install onnxruntime
```

---

## Configure

```python
# app/adapters/http/deps.py
from app.execution.onnx_executor import OnnxExecutor

@lru_cache
def get_onnx_executor():
    return OnnxExecutor(max_workers=4)
```

Register it in `ExecutionPolicy`:

```python
@lru_cache
def get_execution_policy() -> ExecutionPolicy:
    return ExecutionPolicy(
        executors={
            "cpu": get_cpu_executor(),
            "onnx": get_onnx_executor(),
        },
        policy={"my_model:v1": "onnx"},
        default="cpu",
    )
```

---

## Pipeline definition

In your `build_pipeline()`, load the ONNX model using `onnxruntime.InferenceSession`:

```python
import onnxruntime as ort

class MyOnnxModel(BaseModel):
    def load(self) -> None:
        self._session = ort.InferenceSession("model_artifacts/my_model/v1/model.onnx")

    def predict(self, x):
        input_name = self._session.get_inputs()[0].name
        return self._session.run(None, {input_name: x})[0]
```

---

## CLI support

The `deploy` CLI fully supports `.onnx` files and extracts input/output names and shapes automatically.

```bash
inference-engine deploy ./my_model.onnx
```
