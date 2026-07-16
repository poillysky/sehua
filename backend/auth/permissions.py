from __future__ import annotations

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {"*"},
    "operator": {
        "resources.view",
        "crawler.view",
        "import",
        "crawl.run",
        "settings.read",
    },
    "viewer": {
        "resources.view",
        "crawler.view",
    },
}

ROUTE_PERMISSIONS: dict[tuple[str, str], str] = {
    ("GET", "/api/stats"): "resources.view",
    ("GET", "/api/resources/recent"): "resources.view",
    ("GET", "/api/resources/filters"): "resources.view",
    ("GET", "/api/crawl/status"): "crawler.view",
    ("GET", "/api/boards"): "settings.read",
    ("GET", "/api/system/info"): "resources.view",
    ("GET", "/api/system/data-overview"): "settings.write",
    ("POST", "/api/system/reset"): "settings.write",
    ("GET", "/api/system/backup"): "settings.write",
    ("PUT", "/api/system/backup"): "settings.write",
    ("POST", "/api/system/backup/run"): "settings.write",
    ("POST", "/api/import/preview"): "import",
    ("POST", "/api/system/proxy-test"): "settings.read",
    ("GET", "/api/settings"): "settings.read",
    ("PUT", "/api/settings"): "settings.write",
    ("GET", "/api/forum/rules"): "settings.read",
    ("PUT", "/api/forum/active"): "settings.write",
    ("GET", "/api/import/spec"): "settings.read",
    ("POST", "/api/crawl/run"): "crawl.run",
    ("POST", "/api/crawl/enable"): "crawl.run",
    ("GET", "/api/crawler/status"): "crawler.view",
    ("PUT", "/api/crawler/enabled"): "crawl.run",
    ("POST", "/api/crawler/run"): "crawl.run",
    ("POST", "/api/crawler/scan-head"): "crawl.run",
    ("POST", "/api/crawler/random-tid"): "crawl.run",
    ("POST", "/api/crawler/random-tid/loop/start"): "crawl.run",
    ("POST", "/api/crawler/loop/start"): "crawl.run",
    ("POST", "/api/crawler/loop/stop"): "crawl.run",
    ("POST", "/api/crawler/queue/retry-abnormal"): "crawl.run",
    ("POST", "/api/crawler/queue/retry-soft-ad"): "crawl.run",
    ("POST", "/api/crawler/recrawl-stubs"): "crawl.run",
    ("POST", "/api/crawler/stop"): "crawl.run",
    ("POST", "/api/import"): "import",
    ("POST", "/api/import/file"): "import",
    ("GET", "/api/auth/me"): "resources.view",
    ("GET", "/api/auth/users"): "users.manage",
    ("POST", "/api/auth/users"): "users.manage",
    ("PUT", "/api/auth/users/{user_id}"): "users.manage",
    ("DELETE", "/api/auth/users/{user_id}"): "users.manage",
}


def permissions_for_roles(roles: list[str]) -> set[str]:
    perms: set[str] = set()
    for role in roles:
        perms.update(ROLE_PERMISSIONS.get(role, set()))
    return perms


def has_permission(roles: list[str], permission: str) -> bool:
    perms = permissions_for_roles(roles)
    return "*" in perms or permission in perms


def route_permission(method: str, path: str) -> str | None:
    key = (method.upper(), path)
    if key in ROUTE_PERMISSIONS:
        return ROUTE_PERMISSIONS[key]
    if path.startswith("/api/auth/users/"):
        return "users.manage"
    if method == "POST" and path.startswith("/api/forum/") and path.endswith("/link-test"):
        return "settings.read"
    if method == "POST" and path.startswith("/api/forum/") and path.endswith("/parse-thread"):
        return "settings.read"
    if method == "PUT" and path.startswith("/api/forum/") and path.endswith("/config"):
        return "settings.write"
    if method == "PUT" and path.startswith("/api/forum/") and path.endswith("/active-board"):
        return "settings.write"
    if method == "PUT" and path.startswith("/api/forum/") and path.endswith("/enabled-boards"):
        return "settings.write"
    if method == "PUT" and path.startswith("/api/forum/") and path.endswith("/board-order"):
        return "settings.write"
    return None
