"""Issue #57 — ExtractorRegistry TDD tests.

Tests written BEFORE implementation. These define the expected behavior of:
- BaseExtractor (abstract interface)
- ExtractorRegistry (register/resolve/priority ordering)
- Built-in extractors (can_handle + extract for each format)
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURE = Path(__file__).parent / "fixtures" / "sentiment.pkl"


@pytest.fixture
def make_pkl(tmp_path):
    """Create a minimal pickle file."""
    import pickle
    p = tmp_path / "model.pkl"
    p.write_bytes(pickle.dumps({"dummy": True}))
    return p


@pytest.fixture
def make_joblib(tmp_path):
    """Create a minimal joblib file."""
    import joblib
    p = tmp_path / "model.joblib"
    joblib.dump({"dummy": True}, str(p))
    return p


@pytest.fixture
def make_pt(tmp_path):
    """Create a minimal PyTorch state dict file."""
    torch = pytest.importorskip("torch")
    p = tmp_path / "model.pt"
    torch.save({"layer.weight": torch.zeros(4, 4)}, str(p))
    return p


@pytest.fixture
def make_onnx(tmp_path):
    """Create a minimal ONNX model file."""
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


@pytest.fixture
def make_safetensors(tmp_path):
    """Create a minimal safetensors file."""
    pytest.importorskip("safetensors")
    import torch
    from safetensors.torch import save_file
    p = tmp_path / "model.safetensors"
    save_file({"encoder.weight": torch.zeros(8, 4)}, str(p))
    return p


@pytest.fixture
def make_directory(tmp_path):
    """Create a directory with config.json (HF-style)."""
    cfg = {"model_type": "bert", "architectures": ["BertModel"], "hidden_size": 768}
    (tmp_path / "config.json").write_text(json.dumps(cfg))
    return tmp_path


@pytest.fixture
def make_unknown(tmp_path):
    """Create a file with unknown format."""
    p = tmp_path / "model.xyz"
    p.write_bytes(b"\x00" * 100)
    return p


# ---------------------------------------------------------------------------
# BaseExtractor interface tests
# ---------------------------------------------------------------------------

class TestBaseExtractor:
    """Verify the abstract base class contract."""

    def test_cannot_instantiate_directly(self):
        from app.cli.core.extractors.base import BaseExtractor
        with pytest.raises(TypeError):
            BaseExtractor()

    def test_subclass_must_implement_can_handle(self):
        from app.cli.core.extractors.base import BaseExtractor

        class Bad(BaseExtractor):
            name = "bad"
            priority = 50

            def extract(self, path: str, raw_facts: dict) -> dict:
                return raw_facts

        with pytest.raises(TypeError):
            Bad()

    def test_subclass_must_implement_extract(self):
        from app.cli.core.extractors.base import BaseExtractor

        class Bad(BaseExtractor):
            name = "bad"
            priority = 50

            def can_handle(self, path: str, raw_facts: dict) -> bool:
                return True

        with pytest.raises(TypeError):
            Bad()

    def test_valid_subclass_instantiates(self):
        from app.cli.core.extractors.base import BaseExtractor

        class Good(BaseExtractor):
            name = "good"
            priority = 50

            def can_handle(self, path: str, raw_facts: dict) -> bool:
                return True

            def extract(self, path: str, raw_facts: dict) -> dict:
                return raw_facts

        ext = Good()
        assert ext.name == "good"
        assert ext.priority == 50

    def test_has_name_attribute(self):
        from app.cli.core.extractors.base import BaseExtractor

        class Named(BaseExtractor):
            name = "named_ext"
            priority = 10

            def can_handle(self, path: str, raw_facts: dict) -> bool:
                return False

            def extract(self, path: str, raw_facts: dict) -> dict:
                return raw_facts

        assert Named().name == "named_ext"

    def test_has_priority_attribute(self):
        from app.cli.core.extractors.base import BaseExtractor

        class Prioritized(BaseExtractor):
            name = "p"
            priority = 99

            def can_handle(self, path: str, raw_facts: dict) -> bool:
                return False

            def extract(self, path: str, raw_facts: dict) -> dict:
                return raw_facts

        assert Prioritized().priority == 99

    def test_default_priority_is_defined(self):
        """BaseExtractor should define a default priority so subclasses can omit it."""
        from app.cli.core.extractors.base import BaseExtractor

        class DefaultPriority(BaseExtractor):
            name = "dp"

            def can_handle(self, path: str, raw_facts: dict) -> bool:
                return False

            def extract(self, path: str, raw_facts: dict) -> dict:
                return raw_facts

        ext = DefaultPriority()
        assert hasattr(ext, "priority")
        assert isinstance(ext.priority, int)


# ---------------------------------------------------------------------------
# ExtractorRegistry tests
# ---------------------------------------------------------------------------

class TestExtractorRegistry:
    """Verify registry register/resolve/iteration behavior."""

    def _make_extractor(self, name, priority, handles=True):
        from app.cli.core.extractors.base import BaseExtractor

        _handles = handles
        _name = name

        class Ext(BaseExtractor):
            def can_handle(self, path: str, raw_facts: dict) -> bool:
                return _handles

            def extract(self, path: str, raw_facts: dict) -> dict:
                return {**raw_facts, "extractor": _name}

        Ext.name = _name
        Ext.priority = priority
        return Ext()

    def test_register_and_resolve_single(self):
        from app.cli.core.extractors.registry import ExtractorRegistry

        reg = ExtractorRegistry()
        ext = self._make_extractor("test", 50)
        reg.register(ext)
        resolved = reg.resolve("/fake/path.pkl", {"format": "pickle"})
        assert resolved is ext

    def test_resolve_returns_none_when_no_match(self):
        from app.cli.core.extractors.registry import ExtractorRegistry

        reg = ExtractorRegistry()
        ext = self._make_extractor("nope", 50, handles=False)
        reg.register(ext)
        result = reg.resolve("/fake/path.xyz", {"format": "unknown"})
        assert result is None

    def test_resolve_returns_highest_priority_match(self):
        from app.cli.core.extractors.registry import ExtractorRegistry

        reg = ExtractorRegistry()
        low = self._make_extractor("low", 10)
        high = self._make_extractor("high", 90)
        reg.register(low)
        reg.register(high)
        resolved = reg.resolve("/fake/path", {})
        assert resolved.name == "high"

    def test_resolve_priority_order_is_descending(self):
        """Higher priority number = tried first."""
        from app.cli.core.extractors.registry import ExtractorRegistry

        reg = ExtractorRegistry()
        a = self._make_extractor("a", 30)
        b = self._make_extractor("b", 70)
        c = self._make_extractor("c", 50)
        reg.register(a)
        reg.register(b)
        reg.register(c)
        # All can handle, so highest priority wins
        resolved = reg.resolve("/fake", {})
        assert resolved.name == "b"

    def test_resolve_skips_non_matching(self):
        from app.cli.core.extractors.registry import ExtractorRegistry

        reg = ExtractorRegistry()
        no = self._make_extractor("no", 90, handles=False)
        yes = self._make_extractor("yes", 50, handles=True)
        reg.register(no)
        reg.register(yes)
        resolved = reg.resolve("/fake", {})
        assert resolved.name == "yes"

    def test_register_duplicate_name_replaces(self):
        from app.cli.core.extractors.registry import ExtractorRegistry

        reg = ExtractorRegistry()
        first = self._make_extractor("dup", 50)
        second = self._make_extractor("dup", 60)
        reg.register(first)
        reg.register(second)
        # Should have only one registered with that name
        assert len([e for e in reg.list() if e.name == "dup"]) == 1

    def test_list_returns_all_registered(self):
        from app.cli.core.extractors.registry import ExtractorRegistry

        reg = ExtractorRegistry()
        reg.register(self._make_extractor("a", 10))
        reg.register(self._make_extractor("b", 20))
        reg.register(self._make_extractor("c", 30))
        names = [e.name for e in reg.list()]
        assert set(names) == {"a", "b", "c"}

    def test_list_is_sorted_by_priority_descending(self):
        from app.cli.core.extractors.registry import ExtractorRegistry

        reg = ExtractorRegistry()
        reg.register(self._make_extractor("low", 10))
        reg.register(self._make_extractor("mid", 50))
        reg.register(self._make_extractor("high", 90))
        names = [e.name for e in reg.list()]
        assert names == ["high", "mid", "low"]

    def test_unregister_by_name(self):
        from app.cli.core.extractors.registry import ExtractorRegistry

        reg = ExtractorRegistry()
        reg.register(self._make_extractor("removeme", 50))
        reg.unregister("removeme")
        assert reg.resolve("/fake", {}) is None

    def test_unregister_nonexistent_is_silent(self):
        from app.cli.core.extractors.registry import ExtractorRegistry

        reg = ExtractorRegistry()
        # Should not raise
        reg.unregister("ghost")


# ---------------------------------------------------------------------------
# Default registry factory (pre-populated with built-in extractors)
# ---------------------------------------------------------------------------

class TestDefaultRegistry:
    """The default_registry() factory should come pre-loaded with all built-ins."""

    def test_default_registry_has_all_builtins(self):
        from app.cli.core.extractors import default_registry
        reg = default_registry()
        names = {e.name for e in reg.list()}
        expected = {"pickle", "onnx", "safetensors", "pytorch", "directory", "generic"}
        assert expected.issubset(names)

    def test_generic_extractor_is_lowest_priority(self):
        from app.cli.core.extractors import default_registry
        reg = default_registry()
        extractors = reg.list()
        # Last in sorted list = lowest priority
        assert extractors[-1].name == "generic"

    def test_default_registry_returns_new_instance_each_call(self):
        from app.cli.core.extractors import default_registry
        r1 = default_registry()
        r2 = default_registry()
        assert r1 is not r2


# ---------------------------------------------------------------------------
# GenericExtractor (catch-all fallback)
# ---------------------------------------------------------------------------

class TestGenericExtractor:
    """GenericExtractor tries pickle/joblib as last resort."""

    def test_can_handle_always_true(self):
        from app.cli.core.extractors.builtin import GenericExtractor
        ext = GenericExtractor()
        assert ext.can_handle("/any/file.xyz", {"format": "unknown"}) is True
        assert ext.can_handle("/any/file.pkl", {"format": "pickle"}) is True

    def test_has_lowest_priority(self):
        from app.cli.core.extractors.builtin import GenericExtractor
        ext = GenericExtractor()
        assert ext.priority == 0  # lowest

    def test_extract_on_valid_pickle(self, make_pkl):
        from app.cli.core.extractors.builtin import GenericExtractor
        ext = GenericExtractor()
        raw = {"format": "unknown", "errors": []}
        result = ext.extract(str(make_pkl), raw)
        # Should attempt to load and populate framework
        assert "framework" in result

    def test_extract_on_invalid_file_adds_error(self, tmp_path):
        from app.cli.core.extractors.builtin import GenericExtractor
        ext = GenericExtractor()
        bad = tmp_path / "garbage.bin"
        bad.write_bytes(b"\xff\xfe\xfd" * 50)
        raw = {"format": "unknown", "errors": []}
        result = ext.extract(str(bad), raw)
        assert result.get("framework") == "unknown"
        assert len(result["errors"]) > 0


# ---------------------------------------------------------------------------
# PickleExtractor
# ---------------------------------------------------------------------------

class TestPickleExtractor:
    """PickleExtractor handles .pkl, .pickle, .joblib formats."""

    def test_can_handle_pkl(self):
        from app.cli.core.extractors.builtin import PickleExtractor
        ext = PickleExtractor()
        assert ext.can_handle("/path/model.pkl", {"format": "pickle"}) is True

    def test_can_handle_pickle_extension(self):
        from app.cli.core.extractors.builtin import PickleExtractor
        ext = PickleExtractor()
        assert ext.can_handle("/path/model.pickle", {"format": "pickle"}) is True

    def test_can_handle_joblib(self):
        from app.cli.core.extractors.builtin import PickleExtractor
        ext = PickleExtractor()
        assert ext.can_handle("/path/model.joblib", {"format": "joblib"}) is True

    def test_cannot_handle_onnx(self):
        from app.cli.core.extractors.builtin import PickleExtractor
        ext = PickleExtractor()
        assert ext.can_handle("/path/model.onnx", {"format": "onnx"}) is False

    def test_extract_sklearn_fixture(self):
        from app.cli.core.extractors.builtin import PickleExtractor
        ext = PickleExtractor()
        raw = {"format": "pickle", "errors": []}
        result = ext.extract(str(FIXTURE), raw)
        assert result["framework"] == "sklearn"
        assert result["has_predict"] is True

    def test_extract_populates_class_name(self):
        from app.cli.core.extractors.builtin import PickleExtractor
        ext = PickleExtractor()
        raw = {"format": "pickle", "errors": []}
        result = ext.extract(str(FIXTURE), raw)
        assert result["class_name"] == "Pipeline"

    def test_extract_joblib_file(self, make_joblib):
        from app.cli.core.extractors.builtin import PickleExtractor
        ext = PickleExtractor()
        raw = {"format": "joblib", "errors": []}
        result = ext.extract(str(make_joblib), raw)
        assert "class_name" in result

    def test_name(self):
        from app.cli.core.extractors.builtin import PickleExtractor
        assert PickleExtractor().name == "pickle"

    def test_priority_is_above_generic(self):
        from app.cli.core.extractors.builtin import PickleExtractor, GenericExtractor
        assert PickleExtractor().priority > GenericExtractor().priority


# ---------------------------------------------------------------------------
# TorchExtractor
# ---------------------------------------------------------------------------

class TestTorchExtractorUnit:
    """TorchExtractor handles .pt/.pth pytorch format."""

    def test_can_handle_pt(self):
        from app.cli.core.extractors.builtin import TorchExtractor
        ext = TorchExtractor()
        assert ext.can_handle("/path/model.pt", {"format": "pytorch"}) is True

    def test_can_handle_pth(self):
        from app.cli.core.extractors.builtin import TorchExtractor
        ext = TorchExtractor()
        assert ext.can_handle("/path/model.pth", {"format": "pytorch"}) is True

    def test_cannot_handle_pkl(self):
        from app.cli.core.extractors.builtin import TorchExtractor
        ext = TorchExtractor()
        assert ext.can_handle("/path/model.pkl", {"format": "pickle"}) is False

    def test_extract_state_dict(self, make_pt):
        from app.cli.core.extractors.builtin import TorchExtractor
        ext = TorchExtractor()
        raw = {"format": "pytorch", "errors": []}
        result = ext.extract(str(make_pt), raw)
        assert result["framework"] == "pytorch"
        assert result["load_format"] == "state_dict"
        assert "layer.weight" in result["state_dict_keys"]

    def test_extract_param_count(self, make_pt):
        from app.cli.core.extractors.builtin import TorchExtractor
        ext = TorchExtractor()
        raw = {"format": "pytorch", "errors": []}
        result = ext.extract(str(make_pt), raw)
        assert result["param_count"] == 16  # 4*4

    def test_name(self):
        from app.cli.core.extractors.builtin import TorchExtractor
        assert TorchExtractor().name == "pytorch"


# ---------------------------------------------------------------------------
# OnnxExtractor
# ---------------------------------------------------------------------------

class TestOnnxExtractorUnit:
    """OnnxExtractor handles .onnx format."""

    def test_can_handle_onnx(self):
        from app.cli.core.extractors.builtin import OnnxExtractor
        ext = OnnxExtractor()
        assert ext.can_handle("/path/model.onnx", {"format": "onnx"}) is True

    def test_cannot_handle_pt(self):
        from app.cli.core.extractors.builtin import OnnxExtractor
        ext = OnnxExtractor()
        assert ext.can_handle("/path/model.pt", {"format": "pytorch"}) is False

    def test_extract_framework(self, make_onnx):
        from app.cli.core.extractors.builtin import OnnxExtractor
        ext = OnnxExtractor()
        raw = {"format": "onnx", "errors": []}
        result = ext.extract(str(make_onnx), raw)
        assert result["framework"] == "onnx"

    def test_extract_opset(self, make_onnx):
        from app.cli.core.extractors.builtin import OnnxExtractor
        ext = OnnxExtractor()
        raw = {"format": "onnx", "errors": []}
        result = ext.extract(str(make_onnx), raw)
        assert result["opset"] == 17

    def test_extract_op_types(self, make_onnx):
        from app.cli.core.extractors.builtin import OnnxExtractor
        ext = OnnxExtractor()
        raw = {"format": "onnx", "errors": []}
        result = ext.extract(str(make_onnx), raw)
        assert "Relu" in result["op_types"]

    def test_extract_inputs(self, make_onnx):
        from app.cli.core.extractors.builtin import OnnxExtractor
        ext = OnnxExtractor()
        raw = {"format": "onnx", "errors": []}
        result = ext.extract(str(make_onnx), raw)
        assert result["inputs"][0]["name"] == "X"

    def test_name(self):
        from app.cli.core.extractors.builtin import OnnxExtractor
        assert OnnxExtractor().name == "onnx"


# ---------------------------------------------------------------------------
# SafetensorsExtractor
# ---------------------------------------------------------------------------

class TestSafetensorsExtractorUnit:
    """SafetensorsExtractor handles .safetensors format."""

    def test_can_handle_safetensors(self):
        from app.cli.core.extractors.builtin import SafetensorsExtractor
        ext = SafetensorsExtractor()
        assert ext.can_handle("/path/model.safetensors", {"format": "safetensors"}) is True

    def test_cannot_handle_onnx(self):
        from app.cli.core.extractors.builtin import SafetensorsExtractor
        ext = SafetensorsExtractor()
        assert ext.can_handle("/path/model.onnx", {"format": "onnx"}) is False

    def test_extract_tensor_keys(self, make_safetensors):
        from app.cli.core.extractors.builtin import SafetensorsExtractor
        ext = SafetensorsExtractor()
        raw = {"format": "safetensors", "errors": []}
        result = ext.extract(str(make_safetensors), raw)
        assert "encoder.weight" in result["tensor_keys"]

    def test_extract_tensor_shapes(self, make_safetensors):
        from app.cli.core.extractors.builtin import SafetensorsExtractor
        ext = SafetensorsExtractor()
        raw = {"format": "safetensors", "errors": []}
        result = ext.extract(str(make_safetensors), raw)
        assert result["tensor_shapes"]["encoder.weight"] == [8, 4]

    def test_name(self):
        from app.cli.core.extractors.builtin import SafetensorsExtractor
        assert SafetensorsExtractor().name == "safetensors"


# ---------------------------------------------------------------------------
# DirectoryExtractor
# ---------------------------------------------------------------------------

class TestDirectoryExtractorUnit:
    """DirectoryExtractor handles directory artifacts (HF models, TF saved models)."""

    def test_can_handle_directory(self, make_directory):
        from app.cli.core.extractors.builtin import DirectoryExtractor
        ext = DirectoryExtractor()
        assert ext.can_handle(str(make_directory), {"format": "directory", "is_directory": True}) is True

    def test_cannot_handle_file(self, make_pkl):
        from app.cli.core.extractors.builtin import DirectoryExtractor
        ext = DirectoryExtractor()
        assert ext.can_handle(str(make_pkl), {"format": "pickle", "is_directory": False}) is False

    def test_extract_hf_config(self, make_directory):
        from app.cli.core.extractors.builtin import DirectoryExtractor
        ext = DirectoryExtractor()
        raw = {"format": "directory", "is_directory": True, "errors": []}
        result = ext.extract(str(make_directory), raw)
        assert result["framework"] == "transformers"
        assert result["hf_config"]["model_type"] == "bert"

    def test_extract_empty_dir(self, tmp_path):
        from app.cli.core.extractors.builtin import DirectoryExtractor
        ext = DirectoryExtractor()
        raw = {"format": "directory", "is_directory": True, "errors": []}
        result = ext.extract(str(tmp_path), raw)
        assert result["framework"] == "unknown"

    def test_extract_saved_model_pb(self, tmp_path):
        from app.cli.core.extractors.builtin import DirectoryExtractor
        ext = DirectoryExtractor()
        (tmp_path / "saved_model.pb").write_bytes(b"")
        raw = {"format": "directory", "is_directory": True, "errors": []}
        result = ext.extract(str(tmp_path), raw)
        assert result["format"] == "tf_savedmodel"
        assert result["framework"] == "tensorflow"

    def test_name(self):
        from app.cli.core.extractors.builtin import DirectoryExtractor
        assert DirectoryExtractor().name == "directory"


# ---------------------------------------------------------------------------
# Integration: registry resolves the correct extractor for each format
# ---------------------------------------------------------------------------

class TestRegistryIntegration:
    """End-to-end: default_registry resolves correct extractor per artifact."""

    def test_resolves_pickle_for_pkl(self):
        from app.cli.core.extractors import default_registry
        reg = default_registry()
        ext = reg.resolve("/path/model.pkl", {"format": "pickle", "is_directory": False})
        assert ext.name == "pickle"

    def test_resolves_pytorch_for_pt(self):
        from app.cli.core.extractors import default_registry
        reg = default_registry()
        ext = reg.resolve("/path/model.pt", {"format": "pytorch", "is_directory": False})
        assert ext.name == "pytorch"

    def test_resolves_onnx_for_onnx(self):
        from app.cli.core.extractors import default_registry
        reg = default_registry()
        ext = reg.resolve("/path/model.onnx", {"format": "onnx", "is_directory": False})
        assert ext.name == "onnx"

    def test_resolves_safetensors(self):
        from app.cli.core.extractors import default_registry
        reg = default_registry()
        ext = reg.resolve("/path/model.safetensors", {"format": "safetensors", "is_directory": False})
        assert ext.name == "safetensors"

    def test_resolves_directory(self, tmp_path):
        from app.cli.core.extractors import default_registry
        reg = default_registry()
        ext = reg.resolve(str(tmp_path), {"format": "directory", "is_directory": True})
        assert ext.name == "directory"

    def test_resolves_generic_for_unknown(self):
        from app.cli.core.extractors import default_registry
        reg = default_registry()
        ext = reg.resolve("/path/model.xyz", {"format": "unknown", "is_directory": False})
        assert ext.name == "generic"

    def test_custom_extractor_takes_precedence(self):
        """A user-registered extractor with higher priority beats built-ins."""
        from app.cli.core.extractors import default_registry
        from app.cli.core.extractors.base import BaseExtractor

        class CustomOnnx(BaseExtractor):
            name = "custom_onnx"
            priority = 200  # higher than built-in onnx

            def can_handle(self, path: str, raw_facts: dict) -> bool:
                return raw_facts.get("format") == "onnx"

            def extract(self, path: str, raw_facts: dict) -> dict:
                raw_facts["custom"] = True
                return raw_facts

        reg = default_registry()
        reg.register(CustomOnnx())
        ext = reg.resolve("/path/model.onnx", {"format": "onnx", "is_directory": False})
        assert ext.name == "custom_onnx"


# ---------------------------------------------------------------------------
# Backward compatibility: inspect_artifact still works after refactor
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    """Ensure inspect_artifact() still returns same structure after registry refactor."""

    def test_inspect_sklearn_unchanged(self):
        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(FIXTURE))
        assert meta.framework == "sklearn"
        assert meta.class_name == "Pipeline"
        assert meta.input_hint is not None
        assert meta.output_hint is not None
        assert isinstance(meta.raw_facts, dict)

    def test_inspect_pytorch_unchanged(self, make_pt):
        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(make_pt))
        assert meta.framework == "pytorch"
        assert "state_dict_keys" in meta.extra

    def test_inspect_onnx_unchanged(self, make_onnx):
        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(make_onnx))
        assert meta.framework == "onnx"
        assert meta.extra["opset"] == 17

    def test_inspect_directory_unchanged(self, make_directory):
        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(make_directory))
        assert meta.framework == "transformers"

    def test_inspect_unknown_format_falls_back(self, make_unknown):
        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(make_unknown))
        assert meta.framework == "unknown"
        assert len(meta.inspection_errors) > 0
