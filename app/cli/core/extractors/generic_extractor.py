"""GenericExtractor — catch-all fallback that tries pickle/joblib loading."""
from __future__ import annotations

from .base import BaseExtractor


class GenericExtractor(BaseExtractor):
    """Catch-all fallback extractor. Tries pickle/joblib as a last resort.

    Registered with priority 0 so it's always tried last.
    """

    name = "generic"
    priority = 0

    def can_handle(self, path: str, raw_facts: dict) -> bool:
        # Always returns True — this is the fallback
        return True

    def extract(self, path: str, raw_facts: dict) -> dict:
        try:
            from .pickle_extractor import PickleExtractor
            pickle_ext = PickleExtractor()
            return pickle_ext.extract(path, raw_facts)
        except Exception as e:
            raw_facts.setdefault("errors", []).append({"layer": "extraction", "error": str(e)})
            raw_facts["framework"] = "unknown"
            return raw_facts
