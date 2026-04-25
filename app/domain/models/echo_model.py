from typing import Any

from app.domain.models import BaseModel


class EchoModel(BaseModel):
    """Dummy model — returns input unchanged to validate inference flow."""

    def load(self) -> None:
        pass

    def predict(self, x: Any) -> Any:
        return x
