ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "viewer": frozenset({"analytics"}),
    "operator": frozenset({"analytics", "inventory"}),
    "admin": frozenset({"analytics", "inventory", "audit"}),
}


def is_allowed(role: str, provider: str) -> bool:
    return provider in ROLE_PERMISSIONS.get(role, frozenset())
