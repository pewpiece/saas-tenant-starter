from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from apps.projects.models import Project
from apps.projects.permissions import ProjectRolePermission
from apps.projects.serializers import ProjectSerializer


class ProjectViewSet(ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated, ProjectRolePermission]

    def get_queryset(self):
        # Project.objects is tenant-scoped: already filtered to the active
        # org, and raises if no org is active (see TenantManager).
        return Project.objects.all()

    def perform_create(self, serializer):
        # organization is assigned automatically by TenantOwnedModel.save()
        # from the active tenant context; it is never taken from the request.
        serializer.save(created_by=self.request.user)
