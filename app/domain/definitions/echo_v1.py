from app.domain.models import EchoModel
from app.domain.processing import IdentityPreprocessor, IdentityPostprocessor
from app.domain.pipelines import InferencePipeline

MODEL_NAME = "echo"
MODEL_VERSION = "v1"

def build_pipeline() -> InferencePipeline:
    """
    Construct and return a fully loaded inference pipeline
    """
    
    model = EchoModel()
    model.load()
    
    return InferencePipeline(
        preprocessor=IdentityPreprocessor(),
        model=model,
        postprocessor=IdentityPostprocessor(),
    )