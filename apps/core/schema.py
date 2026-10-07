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
