from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from apps.audit.exceptions import AppendOnlyError
from apps.tenants.models import TenantManager, TenantOwnedModel, TenantQuerySet

APPEND_ONLY = "Audit log entries are append-only."


class _AppendOnlyMixin:
    def update(self, **kwargs):
        raise AppendOnlyError(APPEND_ONLY)

    def bulk_update(self, *args, **kwargs):
        raise AppendOnlyError(APPEND_ONLY)

    def delete(self):
        raise AppendOnlyError(APPEND_ONLY)


class AuditQuerySet(_AppendOnlyMixin, TenantQuerySet):
    pass


class AllTenantsAuditQuerySet(_AppendOnlyMixin, models.QuerySet):
    pass


class AuditLogManager(TenantManager.from_queryset(AuditQuerySet)):
    pass


class AuditLogEntry(TenantOwnedModel):
    """One append-only record of something that happened in an organization.

    Rows can be created but never updated or deleted through the ORM
    (instances, querysets and both managers all refuse). They are removed
    only when their organization is deleted (database cascade).
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    # Kept so the trail still says who acted after the user is deleted.
    actor_email = models.EmailField(blank=True)
    action = models.CharField(max_length=64, db_index=True)
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    target_repr = models.CharField(max_length=255, blank=True)
    changes = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = AuditLogManager()
    all_tenants = models.Manager.from_queryset(AllTenantsAuditQuerySet)()

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name_plural = "audit log entries"

    def __str__(self):
        return f"{self.action} by {self.actor_email or 'system'}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AppendOnlyError(APPEND_ONLY)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyError(APPEND_ONLY)
