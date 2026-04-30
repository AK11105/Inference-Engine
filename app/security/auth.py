"""
Environment-variable-based API key configuration.

Format of API_KEYS env var:
    key1:tenant_id:scope1,scope2;key2:tenant_id:scope1

Falls back to hardcoded dev keys when the env var is absent (dev/test only).
"""
import hmac
import os
from dataclasses import dataclass
from typing import Dict, Set


@dataclass(frozen=True)
class Identity:
    api_key: str
    tenant_id: str
    scopes: Set[str]


_FALLBACK_KEYS: Dict[str, Identity] = {
    "dev-key": Identity(
        api_key="dev-key",
        tenant_id="tenant_dev",
        scopes={"predict", "read_models"},
    ),
    "admin-key": Identity(
        api_key="admin-key",
        tenant_id="tenant_admin",
        scopes={"predict", "read_models", "admin"},
    ),
}


def _load_keys() -> Dict[str, Identity]:
    raw = os.environ.get("API_KEYS", "").strip()
    if not raw:
        return _FALLBACK_KEYS

    result: Dict[str, Identity] = {}
    for entry in raw.split(";"):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(":", 2)
        if len(parts) != 3:
            continue
        key, tenant_id, scopes_str = parts
        scopes = {s.strip() for s in scopes_str.split(",") if s.strip()}
        result[key] = Identity(api_key=key, tenant_id=tenant_id, scopes=scopes)

    return result if result else _FALLBACK_KEYS


# Loaded once at import time; reload by calling _load_keys() again in tests.
API_KEYS: Dict[str, Identity] = _load_keys()


def authenticate(api_key: str) -> Identity | None:
    for key, identity in API_KEYS.items():
        if hmac.compare_digest(key, api_key):
            return identity
    return None


def reload_keys() -> None:
    """Re-read API_KEYS from environment. Useful in tests."""
    global API_KEYS
    API_KEYS = _load_keys()
