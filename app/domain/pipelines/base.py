from typing import Any

from app.domain.models.base import BaseModel
from app.domain.processing.pre import BasePreprocessor
from app.domain.processing.post import BasePostprocessor
from app.domain.validation.base import BaseValidator, NoOpValidator


class InferencePipeline:
    """
    Explicit Inference Pipeline:
        Preprocess → Validate → Model → Postprocess

    The validator runs on the preprocessed (model-ready) input so it can
    check shape, dtype, and value ranges in the model's native format.
    Validation is optional; omitting it defaults to NoOpValidator.
    """

    def __init__(
        self,
        preprocessor: BasePreprocessor,
        model: BaseModel,
        postprocessor: BasePostprocessor,
        validator: BaseValidator | None = None,
    ):
        self.preprocessor = preprocessor
        self.model = model
        self.postprocessor = postprocessor
        self.validator = validator or NoOpValidator()

    def run(self, raw_input: Any) -> Any:
        model_input = self.preprocessor.transform(raw_input)
        self.validator.validate(model_input)
        model_output = self.model.predict(model_input)
        return self.postprocessor.transform(model_output)

    def run_batch(self, raw_inputs) -> list:
        """Default batch: sequential run. Override for optimised batching."""
        return [self.run(raw_input) for raw_input in raw_inputs]
