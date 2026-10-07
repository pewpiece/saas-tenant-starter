from django.conf import settings
from django.db import models

from apps.tenants.models import TenantOwnedModel


class Project(TenantOwnedModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    # SET_NULL: a project belongs to its organization, not to whoever created
    # it, so deleting a user never deletes other members' work.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="projects",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name
