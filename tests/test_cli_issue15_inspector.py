"""Issue #15 — format-routing inspector tests."""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "sentiment.pkl"


def _inspect(path):
    from app.cli.core.inspector import inspect_artifact
    return inspect_artifact(str(path))


def _inspect_warn(path):
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        meta = _inspect(path)
    return meta, w


# ---------------------------------------------------------------------------
# New metadata fields
# ---------------------------------------------------------------------------

class TestNewMetadataFields:
    def test_raw_facts_present(self):
        meta = _inspect(FIXTURE)
        assert isinstance(meta.raw_facts, dict)
        assert "artifact_path" in meta.raw_facts

    def test_confidence_present(self):
        meta = _inspect(FIXTURE)
        assert meta.inspection_confidence in ("high", "medium", "low")

    def test_inspection_errors_present(self):
        meta = _inspect(FIXTURE)
        assert isinstance(meta.inspection_errors, list)

    def test_sklearn_confidence_not_low(self):
        meta = _inspect(FIXTURE)
        assert meta.inspection_confidence in ("high", "medium")


# ---------------------------------------------------------------------------
# PyTorch .pt extractor
# ---------------------------------------------------------------------------

class TestTorchExtractor:
    def _make_state_dict(self, tmp_path) -> Path:
        torch = pytest.importorskip("torch")
        sd = {"layer.weight": torch.zeros(4, 4), "layer.bias": torch.zeros(4)}
        p = tmp_path / "model.pt"
        torch.save(sd, str(p))
        return p

    def test_state_dict_detected(self, tmp_path):
        meta = _inspect(self._make_state_dict(tmp_path))
        assert meta.framework == "pytorch"
        assert meta.load_format == "state_dict"

    def test_state_dict_keys_extracted(self, tmp_path):
        meta = _inspect(self._make_state_dict(tmp_path))
        assert "layer.weight" in meta.extra["state_dict_keys"]

    def test_param_count_extracted(self, tmp_path):
        meta = _inspect(self._make_state_dict(tmp_path))
        assert meta.extra["param_count"] == 20  # 4*4 + 4

    def test_input_output_hints(self, tmp_path):
        meta = _inspect(self._make_state_dict(tmp_path))
        assert meta.input_hint == "torch.Tensor"
        assert meta.output_hint == "torch.Tensor"

    def test_pth_extension(self, tmp_path):
        torch = pytest.importorskip("torch")
        p = tmp_path / "model.pth"
        torch.save({"w": torch.zeros(2)}, str(p))
        meta = _inspect(p)
        assert meta.framework == "pytorch"


# ---------------------------------------------------------------------------
# ONNX extractor
# ---------------------------------------------------------------------------

class TestOnnxExtractor:
    def _make_onnx(self, tmp_path) -> Path:
        onnx = pytest.importorskip("onnx")
        from onnx import helper, TensorProto
        X = helper.make_tensor_value_info("X", TensorProto.FLOAT, [None, 4])
        Y = helper.make_tensor_value_info("Y", TensorProto.FLOAT, [None, 2])
        node = helper.make_node("Relu", ["X"], ["Y"])
        graph = helper.make_graph([node], "test", [X], [Y])
        model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
        p = tmp_path / "model.onnx"
        onnx.save(model, str(p))
        return p

    def test_framework_detected(self, tmp_path):
        assert _inspect(self._make_onnx(tmp_path)).framework == "onnx"

    def test_opset_extracted(self, tmp_path):
        assert _inspect(self._make_onnx(tmp_path)).extra["opset"] == 17

    def test_op_types_extracted(self, tmp_path):
        assert "Relu" in _inspect(self._make_onnx(tmp_path)).extra["op_types"]

    def test_inputs_extracted(self, tmp_path):
        inputs = _inspect(self._make_onnx(tmp_path)).extra["onnx_inputs"]
        assert inputs[0]["name"] == "X"
        assert len(inputs[0]["shape"]) == 2

    def test_dynamic_axis_preserved(self, tmp_path):
        """Named dim_param (e.g. 'batch_size') is kept as a string, not 0."""
        onnx = pytest.importorskip("onnx")
        from onnx import helper, TensorProto
        # Use a named dynamic axis so dim_param is set
        X = helper.make_tensor_value_info("X", TensorProto.FLOAT, ["batch_size", 4])
        Y = helper.make_tensor_value_info("Y", TensorProto.FLOAT, ["batch_size", 2])
        node = helper.make_node("Relu", ["X"], ["Y"])
        graph = helper.make_graph([node], "test", [X], [Y])
        model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
        p = tmp_path / "named_dynamic.onnx"
        onnx.save(model, str(p))
        shape = _inspect(p).extra["onnx_inputs"][0]["shape"]
        assert shape[0] == "batch_size"


# ---------------------------------------------------------------------------
# Safetensors extractor
# ---------------------------------------------------------------------------

class TestSafetensorsExtractor:
    def _make_safetensors(self, tmp_path) -> Path:
        pytest.importorskip("safetensors")
        import torch
        from safetensors.torch import save_file
        p = tmp_path / "model.safetensors"
        save_file({"encoder.weight": torch.zeros(8, 4), "encoder.bias": torch.zeros(8)}, str(p))
        return p

    def test_framework_detected(self, tmp_path):
        assert _inspect(self._make_safetensors(tmp_path)).framework in ("safetensors", "pytorch")

    def test_tensor_keys_extracted(self, tmp_path):
        assert "encoder.weight" in _inspect(self._make_safetensors(tmp_path)).extra["tensor_keys"]

    def test_tensor_shapes_extracted(self, tmp_path):
        shapes = _inspect(self._make_safetensors(tmp_path)).extra["tensor_shapes"]
        assert shapes["encoder.weight"] == [8, 4]


# ---------------------------------------------------------------------------
# Directory extractor
# ---------------------------------------------------------------------------

class TestDirectoryExtractor:
    def test_config_json_transformers(self, tmp_path):
        cfg = {"model_type": "bert", "architectures": ["BertForSequenceClassification"],
               "hidden_size": 768, "num_labels": 2, "num_hidden_layers": 12}
        (tmp_path / "config.json").write_text(json.dumps(cfg))
        meta = _inspect(tmp_path)
        assert meta.framework == "transformers"
        assert meta.extra["hf_config"]["model_type"] == "bert"
        assert meta.extra["hf_config"]["num_labels"] == 2

    def test_tokenizer_config(self, tmp_path):
        (tmp_path / "config.json").write_text(json.dumps({"model_type": "gpt2"}))
        (tmp_path / "tokenizer_config.json").write_text(json.dumps({"tokenizer_class": "GPT2Tokenizer"}))
        assert _inspect(tmp_path).extra.get("tokenizer_class") == "GPT2Tokenizer"

    def test_saved_model_pb(self, tmp_path):
        (tmp_path / "saved_model.pb").write_bytes(b"")
        assert _inspect(tmp_path).raw_facts.get("format") == "tf_savedmodel"

    def test_adapter_config(self, tmp_path):
        (tmp_path / "config.json").write_text(json.dumps({"model_type": "llama"}))
        (tmp_path / "adapter_config.json").write_text(json.dumps({}))
        assert _inspect(tmp_path).raw_facts.get("is_peft_adapter") is True

    def test_empty_directory(self, tmp_path):
        assert _inspect(tmp_path).framework == "unknown"


# ---------------------------------------------------------------------------
# Graceful fallback
# ---------------------------------------------------------------------------

class TestGracefulFallback:
    def test_bad_bytes_warns_not_raises(self, tmp_path):
        p = tmp_path / "model.pkl"
        p.write_bytes(b"\x08\x00\x00\x00" + b"\x00" * 100)
        meta, w = _inspect_warn(p)
        assert meta.framework == "unknown"
        assert len(w) == 1
        assert "partial metadata" in str(w[0].message)

    def test_inspection_errors_populated(self, tmp_path):
        p = tmp_path / "model.pkl"
        p.write_bytes(b"\xff\xfe" + b"\x00" * 50)
        meta, _ = _inspect_warn(p)
        assert len(meta.inspection_errors) > 0
