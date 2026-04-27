# Artifact Loaders

**Files:** `app/domain/loading/`

Loaders abstract artifact retrieval from any storage backend. They are used inside `build_pipeline()` functions — the registry itself never calls a loader directly.

---

## ModelLoader (interface)

```python
# app/domain/loading/base.py
class ModelLoader(ABC):
    def load(self, model_name: str, version: str) -> Path: ...
```

Returns a local `Path` to the artifact directory. Implementations may download files to a temp dir. The caller must not delete the path while the model is in use.

---

## LocalModelLoader

```python
from app.domain.loading.local_loader import LocalModelLoader

loader = LocalModelLoader(root="model_artifacts")  # default: "model_artifacts"
path = loader.load("my_model", "v1")
# → Path("model_artifacts/my_model/v1/")
```

Expects artifacts at `<root>/<model_name>/<version>/`. Raises `FileNotFoundError` if the directory does not exist.

---

## S3ModelLoader

```python
from app.domain.loading.s3_loader import S3ModelLoader

loader = S3ModelLoader(bucket="my-bucket", prefix="models")
path = loader.load("my_model", "v1")
# downloads s3://my-bucket/models/my_model/v1/* → local temp dir
```

Downloads all objects under `s3://<bucket>/<prefix>/<model>/<version>/` to a `tempfile.mkdtemp()` directory and returns that path.

Raises `FileNotFoundError` if no objects are found at the prefix.  
Raises `RuntimeError` if `boto3` is not installed.

**Requires:** `pip install boto3`

---

## Usage in a pipeline definition

```python
def build_pipeline() -> InferencePipeline:
    loader = LocalModelLoader(root="model_artifacts")
    artifact_path = loader.load("my_model", "v1")

    model = MyModel(artifact_path / "model.pkl")
    model.load()
    return InferencePipeline(...)
```

`build_pipeline()` is called once at startup. The loader runs once; the returned path is valid for the lifetime of the process.
