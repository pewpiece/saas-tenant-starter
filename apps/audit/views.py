from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from apps.audit.models import AuditLogEntry
from apps.audit.serializers import AuditLogEntrySerializer
from apps.tenants.permissions import IsTenantAdmin
from apps.tenants.views import TenantScopedViewMixin


class AuditLogListView(TenantScopedViewMixin, generics.ListAPIView):
    """The active organization's audit log, newest first (admins and owners).

    Filter with `?action=project.update`.
    """

    serializer_class = AuditLogEntrySerializer
    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def get_queryset(self):
        return self.tenant_queryset(self._entries, AuditLogEntry.all_tenants.none())

    def _entries(self):
        queryset = AuditLogEntry.objects.all()
        action = self.request.query_params.get("action")
        if action:
            queryset = queryset.filter(action=action)
        return queryset
