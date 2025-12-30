from dataclasses import dataclass
from typing import Dict, Set

@dataclass(frozen=True)
class Identity:
    api_key: str
    tenant_id: str
    scopes: Set[str]
    
#In Memory key store (SWAP FOR DB in future)
API_KEYS: Dict[str, Identity] = {
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

def authenticate(api_key: str) -> Identity | None:
    return API_KEYS.get(api_key)