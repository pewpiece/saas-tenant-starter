from django.conf import settings
from django.db import models

from apps.tenants.context import get_current_org
from apps.tenants.exceptions import NoActiveTenantError


class Organization(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.slug


class Membership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "organization")

    def __str__(self):
        return f"{self.user_id}@{self.organization_id} ({self.role})"


class TenantManager(models.Manager):
    """Default manager for TenantOwnedModel subclasses.

    Auto-filters every query by the current org (from the request-scoped
    contextvar) and raises loudly instead of silently returning cross-tenant
    rows when no org is active. Admin/system code that genuinely needs to
    operate across tenants should use the model's `all_tenants` manager
    instead of working around this.
    """

    def get_queryset(self):
        org = get_current_org()
        if org is None:
            raise NoActiveTenantError(
                f"{self.model.__name__}.objects was queried with no active "
                "tenant. Use set_current_org() (normally done for you by "
                "TenantMiddleware), or use "
                f"{self.model.__name__}.all_tenants for admin/system access."
            )
        return super().get_queryset().filter(organization=org)


class TenantOwnedModel(models.Model):
    """Abstract base for every tenant-owned table.

    Adds the `organization` FK, auto-assigns it from the active tenant on
    create, and exposes two managers:
      - `objects` (TenantManager): the default; filtered to the active org,
        raises if none is active.
      - `all_tenants` (plain Manager): unfiltered, for admin/system use only.
    """

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, editable=False
    )

    objects = TenantManager()
    all_tenants = models.Manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self._state.adding and not self.organization_id:
            org = get_current_org()
            if org is None:
                raise NoActiveTenantError(
                    f"Cannot create a {type(self).__name__} with no active "
                    "tenant and no explicit organization set."
                )
            self.organization = org
        super().save(*args, **kwargs)
