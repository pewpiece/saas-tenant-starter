"""Discover the API's routes from the URLconf, for the generated QA suites."""

import re
from dataclasses import dataclass

from django.urls import URLResolver, get_resolver
from rest_framework.views import APIView

from apps.tenants.views import TenantScopedViewMixin

PK_GROUP = re.compile(r"\(\?P<pk>[^)]*\)")


@dataclass(frozen=True)
class Route:
    pattern: str  # e.g. "api/projects/{pk}/"
    view: type
    methods: tuple  # lower-case HTTP methods the route serves

    @property
    def is_detail(self):
        return "{pk}" in self.pattern

    @property
    def is_tenant_scoped(self):
        return issubclass(self.view, TenantScopedViewMixin)

    def url(self, pk=None):
        return "/" + self.pattern.replace("{pk}", str(pk))

    def __str__(self):
        return self.pattern


def _walk(resolver, prefix=""):
    for entry in resolver.url_patterns:
        if isinstance(entry, URLResolver):
            yield from _walk(entry, prefix + str(entry.pattern))
        else:
            yield prefix + str(entry.pattern), entry


def _normalise(raw):
    return PK_GROUP.sub("{pk}", raw).replace("^", "").replace("$", "")


def _methods(callback, view):
    actions = getattr(callback, "actions", None)
    if actions:
        allowed = set(view.http_method_names)
        return tuple(sorted(m for m in actions if m in allowed))
    return tuple(
        sorted(m for m in view.http_method_names if m not in ("options", "head") and hasattr(view, m))
    )


def api_routes():
    routes = []
    for raw, entry in _walk(get_resolver()):
        view = getattr(entry.callback, "cls", None)
        if not raw.startswith("api/") or view is None or not issubclass(view, APIView):
            continue
        routes.append(Route(_normalise(raw), view, _methods(entry.callback, view)))
    return sorted(routes, key=lambda r: r.pattern)
