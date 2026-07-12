"""PickleExtractor — handles .pkl, .pickle, .joblib serialized objects."""
from __future__ import annotations

from .base import BaseExtractor


class PickleExtractor(BaseExtractor):
    """Handles pickle/joblib serialized Python objects (sklearn, etc.)."""

    name = "pickle"
    priority = 60

    _FORMATS = {"pickle", "joblib"}

    def can_handle(self, path: str, raw_facts: dict) -> bool:
        return raw_facts.get("format") in self._FORMATS

    def extract(self, path: str, raw_facts: dict) -> dict:
        try:
            import joblib
            obj = joblib.load(path)
            raw_facts["load_via"] = "joblib"
        except Exception:
            import pickle
            with open(path, "rb") as f:
                obj = pickle.load(f)
            raw_facts["load_via"] = "pickle"

        raw_facts["class_name"] = type(obj).__name__
        raw_facts["module"] = type(obj).__module__ or ""
        try:
            raw_facts["attributes"] = list(vars(obj).keys())
        except Exception:
            raw_facts["attributes"] = []
        raw_facts["has_predict"] = hasattr(obj, "predict")
        raw_facts["has_predict_proba"] = hasattr(obj, "predict_proba")
        raw_facts["has_steps"] = hasattr(obj, "steps")

        # Framework detection
        framework = "generic"
        module = raw_facts["module"]

        try:
            from sentence_transformers import SentenceTransformer
            if isinstance(obj, SentenceTransformer):
                framework = "sentence_transformers"
        except Exception:
            pass

        if framework == "generic":
            try:
                from transformers import PreTrainedModel
                if isinstance(obj, PreTrainedModel):
                    framework = "transformers"
            except Exception:
                pass

        if framework == "generic":
            try:
                import torch
                if isinstance(obj, torch.nn.Module):
                    framework = "pytorch"
            except Exception:
                pass

        if framework == "generic":
            try:
                import xgboost as xgb
                if isinstance(obj, (xgb.XGBModel, xgb.Booster)):
                    framework = "xgboost"
            except Exception:
                pass

        if framework == "generic":
            try:
                import lightgbm as lgb
                if isinstance(obj, (lgb.Booster, lgb.LGBMModel)):
                    framework = "lightgbm"
            except Exception:
                pass

        if framework == "generic":
            try:
                from catboost import CatBoost
                if isinstance(obj, CatBoost):
                    framework = "catboost"
            except Exception:
                pass

        if framework == "generic" and "sklearn" in module:
            framework = "sklearn"

        raw_facts["framework"] = framework

        # Deep attribute scan
        try:
            if framework == "sklearn":
                if hasattr(obj, "steps"):
                    raw_facts["pipeline_steps"] = [type(s).__name__ for _, s in obj.steps]
                if hasattr(obj, "n_features_in_"):
                    raw_facts["n_features_in"] = int(obj.n_features_in_)
                if hasattr(obj, "classes_"):
                    raw_facts["classes"] = obj.classes_.tolist()
                elif hasattr(obj, "steps"):
                    for _, step in obj.steps:
                        if hasattr(step, "classes_"):
                            raw_facts["classes"] = step.classes_.tolist()
                            break

            elif framework == "pytorch":
                import torch
                layer_count = sum(1 for _ in obj.modules())
                raw_facts["layer_count"] = layer_count
                children = list(obj.named_children())
                if children:
                    raw_facts["first_layer"] = type(children[0][1]).__name__
                    raw_facts["last_layer"] = type(children[-1][1]).__name__

            elif framework == "transformers":
                cfg = obj.config
                raw_facts["model_type"] = getattr(cfg, "model_type", None)
                raw_facts["hidden_size"] = getattr(cfg, "hidden_size", None)
                raw_facts["num_labels"] = getattr(cfg, "num_labels", None)
                raw_facts["tokenizer_class"] = getattr(cfg, "tokenizer_class", None)

            elif framework == "xgboost":
                import xgboost as xgb
                if isinstance(obj, xgb.XGBModel):
                    raw_facts["n_estimators"] = getattr(obj, "n_estimators", None)
                    raw_facts["objective"] = getattr(obj, "objective", None)
                    if hasattr(obj, "n_features_in_"):
                        raw_facts["n_features_in"] = int(obj.n_features_in_)
                elif isinstance(obj, xgb.Booster):
                    raw_facts["num_trees"] = obj.num_trees()

            elif framework == "lightgbm":
                import lightgbm as lgb
                if isinstance(obj, lgb.LGBMModel):
                    raw_facts["n_estimators"] = getattr(obj, "n_estimators", None)
                    raw_facts["objective"] = getattr(obj, "objective", None)
                    if hasattr(obj, "n_features_in_"):
                        raw_facts["n_features_in"] = int(obj.n_features_in_)
                elif isinstance(obj, lgb.Booster):
                    raw_facts["num_trees"] = obj.num_trees()

            elif framework == "catboost":
                from catboost import CatBoost
                raw_facts["loss_function"] = obj.get_param("loss_function")
                fc = obj.get_param("feature_count") or obj.get_param("num_features")
                if fc is not None:
                    raw_facts["n_features_in"] = int(fc)

            elif framework == "sentence_transformers":
                raw_facts["model_name"] = (
                    getattr(obj, "_model_card_text", None) or type(obj).__name__
                )
                for m in obj.modules():
                    if hasattr(m, "word_embedding_dimension"):
                        raw_facts["embedding_dim"] = m.word_embedding_dimension
                        break

        except Exception as e:
            raw_facts.setdefault("errors", []).append({"layer": "deep", "error": str(e)})

        return raw_facts
