def require_scope(identity, scope: str) -> None:
    if scope not in identity.scopes:
        raise PermissionError(f"Missing Scope: {scope}")