import random
import hashlib
from typing import Tuple

class RoutingService:
    def __init__(self, routes: dict):
        self._routes = routes
    
    def resolve(
        self,
        model: str,
        requested_version: str | None,
        identity_key: str | None,
    ) -> Tuple[str, str]:
        """
        Resolve (model, version) to execute
        """
        
        # Explicit version always wins
        if requested_version:
            return model, requested_version
        
        route = self._routes.get(model)
        if not route:
            raise ValueError(f"No routing configuration for model '{model}'")
        
        strategy = route["strategy"]
        
        if strategy == "static":
            return model, route["version"]
        
        if strategy == "canary":
            pct = route["canary_percent"]
            if random.randint(1, 100) < pct:
                return model, route["canary"]
            return model, route["primary"]
        
        if strategy == "ab":
            if not identity_key:
                raise ValueError("A/B routing requires identity key")
            
            h = int(hashlib.sha256(identity_key.encode()).hexdigest(), 16)
            bucket = h % 100
            
            acc = 0
            for version, weight in route["variants"].items():
                acc += weight
                if bucket < acc:
                    return model, version
        
        raise ValueError(f"Invalid routing strategy for model '{model}'")