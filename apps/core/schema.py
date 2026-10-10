from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.utils import OpenApiParameter

from apps.tenants.views import TENANT_HEADER, TenantScopedViewMixin


class TenantAwareAutoSchema(AutoSchema):
    """Documents the required X-Org header on every tenant-scoped view."""

    def get_override_parameters(self):
        params = super().get_override_parameters()
        if isinstance(self.view, TenantScopedViewMixin):
            params = [
                OpenApiParameter(
                    TENANT_HEADER,
                    str,
                    OpenApiParameter.HEADER,
                    required=True,
                    description="Slug of the organization (tenant) to act in.",
                ),
                *params,
            ]
        return params


class ThrottledBasicAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.core.authentication.ThrottledBasicAuthentication"
    name = "basicAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "basic"}


class BearerTokenAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.core.authentication.BearerTokenAuthentication"
    name = "bearerAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer"}


ERROR_SCHEMA = {
    "type": "object",
    "description": (
        "Error body. `detail` holds the message; validation errors map field "
        "names to lists of messages instead."
    ),
    "properties": {"detail": {"type": "string"}},
    "additionalProperties": True,
}

ERROR_DESCRIPTIONS = {
    "400": "Invalid request (validation error or malformed body).",
    "401": "Missing or invalid credentials (`WWW-Authenticate: Basic`).",
    "403": "Forbidden: not a member of the X-Org organization, role too low, or plan limit.",
    "404": "Not found in this organization (or page out of range).",
    "409": "Conflict: an organization must keep at least one owner.",
    "429": "Too many requests or failed logins.",
}

PUBLIC_DOCS = ("/api/schema/", "/api/docs/")
NO_AUTH = ("/api/auth/signup/",)
LAST_OWNER_PATHS = ("/api/members/{id}/",)


def add_error_responses(result, generator, request, public):
    """drf-spectacular post-processing hook: document the error responses.

    drf-spectacular only documents success responses by default, so clients
    and fuzzers (Schemathesis) saw every 4xx as undocumented (D-17).
    """
    result.setdefault("components", {}).setdefault("schemas", {})["Error"] = ERROR_SCHEMA
    for path, operations in result["paths"].items():
        if path in PUBLIC_DOCS:
            continue
        for method, operation in operations.items():
            codes = {"429"}
            if path not in NO_AUTH:
                codes |= {"401", "403"}
            if method in ("post", "put", "patch", "delete"):
                codes.add("400")
            if "{id}" in path or method == "get":
                codes.add("404")
            if path in LAST_OWNER_PATHS and method in ("patch", "put", "delete"):
                codes.add("409")
            responses = operation.setdefault("responses", {})
            for code in sorted(codes):
                responses.setdefault(
                    code,
                    {
                        "description": ERROR_DESCRIPTIONS[code],
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Error"}}
                        },
                    },
                )
    return result
