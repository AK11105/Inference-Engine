from typing import Any 

from app.domain.models import BaseModel
from app.domain.processing import BasePreprocessor, BasePostprocessor

class InferencePipeline:
    """
    Explicit Inference Pipeline
    Preprocess -> Model Output -> Postprocess
    """
    
    def __init__(
        self,
        preprocessor: BasePreprocessor,
        model: BaseModel,
        postprocessor: BasePostprocessor
        ):
        self.preprocessor = preprocessor
        self.model = model
        self.postprocessor = postprocessor
    
    def run(self, raw_input: Any) -> Any:
        """
        Execute full inference pipeline
        """
        model_input = self.preprocessor.transform(raw_input)
        model_output = self.model.predict(model_input)
        return self.postprocessor.transform(model_output)
    
    def run_batch(self, raw_inputs):
        """
        Default batch behavior: fallback to sequential run
        Models may override for optimized batching
        """
        return [self.run(raw_input) for raw_input in raw_inputs]