from django.contrib import admin

from apps.audit.models import AuditLogEntry


@admin.register(AuditLogEntry)
class AuditLogEntryAdmin(admin.ModelAdmin):
    """Read-only, cross-tenant view of the audit log."""

    list_display = ("created_at", "organization", "action", "actor_email", "target_repr")
    list_filter = ("action", "organization")
    search_fields = ("actor_email", "target_repr", "action")

    def get_queryset(self, request):
        return AuditLogEntry.all_tenants.select_related("organization")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
