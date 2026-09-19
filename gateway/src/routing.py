"""Gateway routing table per contracts/gateway-routing.md.

The Gateway is the only network-facing entry point for backend services; services do not
need their own public ingress or duplicate auth logic.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Route:
    prefix: str
    upstream_base_url_setting: str
    public_paths: tuple[str, ...] = ()


ROUTES: list[Route] = [
    Route(
        prefix="/api/v1/identity",
        upstream_base_url_setting="identity_base_url",
        public_paths=("/api/v1/identity/auth/login",),
    ),
    Route(prefix="/api/v1/query", upstream_base_url_setting="query_api_base_url"),
    Route(prefix="/api/v1/alerting", upstream_base_url_setting="alerting_base_url"),
    Route(prefix="/api/v1/realtime", upstream_base_url_setting="realtime_base_url"),
]


def resolve_route(path: str) -> Route | None:
    for route in ROUTES:
        if path.startswith(route.prefix):
            return route
    return None


def is_public(path: str) -> bool:
    route = resolve_route(path)
    return route is not None and path in route.public_paths
