"""OnnxExtractor — handles .onnx model files."""
from __future__ import annotations

from .base import BaseExtractor


class OnnxExtractor(BaseExtractor):
    """Handles ONNX model files (.onnx)."""

    name = "onnx"
    priority = 60

    def can_handle(self, path: str, raw_facts: dict) -> bool:
        return raw_facts.get("format") == "onnx"

    def extract(self, path: str, raw_facts: dict) -> dict:
        import onnx

        model = onnx.load(path)
        raw_facts["framework"] = "onnx"
        raw_facts["opset"] = model.opset_import[0].version if model.opset_import else None
        raw_facts["op_types"] = list({n.op_type for n in model.graph.node})

        def _shape(tensor_type):
            if not tensor_type.HasField("shape"):
                return []
            return [
                d.dim_param if d.dim_param else d.dim_value
                for d in tensor_type.shape.dim
            ]

        raw_facts["inputs"] = [
            {"name": i.name, "shape": _shape(i.type.tensor_type), "dtype": i.type.tensor_type.elem_type}
            for i in model.graph.input
        ]
        raw_facts["outputs"] = [
            {"name": o.name, "shape": _shape(o.type.tensor_type), "dtype": o.type.tensor_type.elem_type}
            for o in model.graph.output
        ]

        return raw_facts
