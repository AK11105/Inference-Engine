from app.domain.models.base import BaseModel
from app.domain.processing.pre import IdentityPreprocessor
from app.domain.processing.post import IdentityPostprocessor
from app.domain.pipelines.base import InferencePipeline

MODEL_NAME = 'sentiment'
MODEL_VERSION = 'v1'

class _GeneratedModel(BaseModel):
    def load(self) -> None:
        import pickle
        with open(r'C:\Users\Atharva Kulkarni\Desktop\Programming\ML PROJECTS\ML-Backend\Inference-Engine\tests\fixtures\sentiment.pkl', 'rb') as f:
            self._model = pickle.load(f)

    def predict(self, x):
        return self._model.predict([x])[0]

def build_pipeline() -> InferencePipeline:
    model = _GeneratedModel()
    model.load()
    return InferencePipeline(
        preprocessor=IdentityPreprocessor(),
        model=model,
        postprocessor=IdentityPostprocessor(),
    )
