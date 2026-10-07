from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from apps.audit.services import diff, record
from apps.billing.services import ensure_can_add_project, lock_organization
from apps.projects.models import Project
from apps.projects.permissions import ProjectRolePermission
from apps.projects.serializers import ProjectSerializer
from apps.tenants.views import TenantScopedViewMixin

AUDITED_FIELDS = ("name", "description")


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
