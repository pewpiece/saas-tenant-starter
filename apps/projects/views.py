import csv

from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from apps.audit.services import diff, record
from apps.billing.plans import PROJECT_EXPORT
from apps.billing.services import ensure_can_add_project, ensure_feature, lock_organization
from apps.projects.models import Project
from apps.projects.permissions import ProjectRolePermission
from apps.projects.serializers import ProjectSerializer
from apps.tenants.views import TenantScopedViewMixin

AUDITED_FIELDS = ("name", "description")
EXPORT_COLUMNS = ["id", "name", "description", "created_by", "created_at"]
# Spreadsheet apps execute cells starting with these as formulas.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value):
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(FORMULA_PREFIXES) else text


class ProjectViewSet(TenantScopedViewMixin, ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated, ProjectRolePermission]

    def get_queryset(self):
        # Project.objects is tenant-scoped: already filtered to the active
        # org, and raises if no org is active (see TenantManager).
        return self.tenant_queryset(
            lambda: Project.objects.select_related("organization"), Project.all_tenants.none()
        )

    def perform_create(self, serializer):
        lock_organization(self.request.tenant)
        ensure_can_add_project(self.request.tenant)
        # organization is assigned automatically by TenantOwnedModel.save()
        # from the active tenant context; it is never taken from the request.
        project = serializer.save(created_by=self.request.user)
        record("project.create", actor=self.request.user, target=project, changes={"name": project.name})

    def perform_update(self, serializer):
        old = {field: getattr(serializer.instance, field) for field in AUDITED_FIELDS}
        project = serializer.save()
        changes = diff(project, old, AUDITED_FIELDS)
        if changes:
            record("project.update", actor=self.request.user, target=project, changes=changes)

    def perform_destroy(self, instance):
        record("project.delete", actor=self.request.user, target=instance, changes={"name": instance.name})
        instance.delete()

    @extend_schema(responses={(200, "text/csv"): OpenApiResponse(OpenApiTypes.STR)})
    @action(detail=False, methods=["get"], url_path="export")
    def export(self, request):
        """Download the organization's projects as CSV (Pro plan only)."""
        ensure_feature(request.tenant, PROJECT_EXPORT)
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{request.tenant.slug}-projects.csv"'
        writer = csv.writer(response)
        writer.writerow(EXPORT_COLUMNS)
        for project in Project.objects.select_related("created_by").order_by("id"):
            writer.writerow(
                [
                    project.id,
                    _csv_safe(project.name),
                    _csv_safe(project.description),
                    _csv_safe(project.created_by.email if project.created_by else ""),
                    project.created_at.isoformat(),
                ]
            )
        record("project.export", actor=request.user, changes={"format": "csv"})
        return response
