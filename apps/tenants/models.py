import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from apps.tenants.context import get_current_org
from apps.tenants.exceptions import (
    LastOwnerError,
    NoActiveTenantError,
    TenantMismatchError,
    UnscopedQueryError,
)

ORGANIZATION_FIELDS = frozenset({"organization", "organization_id"})


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

    def _is_last_owner(self):
        return not (
            Membership.objects.filter(organization_id=self.organization_id, role=self.Role.OWNER)
            .exclude(pk=self.pk)
            .exists()
        )

    def _lock_organization(self):
        # Serialise owner changes per org, so two owners demoting each other
        # concurrently cannot both pass the last-owner check.
        Organization.objects.select_for_update().filter(pk=self.organization_id).first()

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if not self._state.adding and self.role != self.Role.OWNER:
                self._lock_organization()
                stored_role = (
                    Membership.objects.filter(pk=self.pk).values_list("role", flat=True).first()
                )
                if stored_role == self.Role.OWNER and self._is_last_owner():
                    raise LastOwnerError("An organization must keep at least one owner.")
            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Cascades (deleting the organization) do not call Model.delete(), so
        # this only guards removing a single membership.
        with transaction.atomic():
            self._lock_organization()
            if self.role == self.Role.OWNER and self._is_last_owner():
                raise LastOwnerError("An organization must keep at least one owner.")
            return super().delete(*args, **kwargs)


class TenantQuerySet(models.QuerySet):
    """QuerySet for the tenant-scoped manager.

    Closes the ORM paths that skip TenantOwnedModel.save() or the tenant
    filter: bulk_create, bulk_update, update and raw.
    """

    def update(self, **kwargs):
        if ORGANIZATION_FIELDS & kwargs.keys():
            raise TenantMismatchError("A row's organization cannot be changed.")
        return super().update(**kwargs)

    def bulk_create(self, objs, *args, **kwargs):
        objs = list(objs)
        org = _require_active_org(self.model)
        for obj in objs:
            obj._assign_or_check_organization(org)
        return super().bulk_create(objs, *args, **kwargs)

    def bulk_update(self, objs, fields, *args, **kwargs):
        if ORGANIZATION_FIELDS & set(fields):
            raise TenantMismatchError("A row's organization cannot be changed.")
        objs = list(objs)
        org = _require_active_org(self.model)
        for obj in objs:
            if obj.organization_id != org.id:
                raise TenantMismatchError(_mismatch_message(obj, org))
        return super().bulk_update(objs, fields, *args, **kwargs)

    def raw(self, *args, **kwargs):
        raise UnscopedQueryError(
            f"{self.model.__name__}.objects.raw() cannot be tenant-scoped. Use "
            f"{self.model.__name__}.all_tenants.raw() and filter on organization_id."
        )


def _require_active_org(model):
    org = get_current_org()
    if org is None:
        raise NoActiveTenantError(
            f"{model.__name__}.objects was queried with no active tenant. Use "
            "tenant_context(org) (done for you by TenantScopedViewMixin), or use "
            f"{model.__name__}.all_tenants for admin/system access."
        )
    return org


def _mismatch_message(obj, org):
    return (
        f"{type(obj).__name__} belongs to organization {obj.organization_id}, "
        f"but the active tenant is {org.id}."
    )


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    """Default manager for TenantOwnedModel subclasses.

    Auto-filters every query by the current org (from the request-scoped
    contextvar) and raises loudly instead of silently returning cross-tenant
    rows when no org is active. Admin/system code that genuinely needs to
    operate across tenants should use the model's `all_tenants` manager
    instead of working around this.

    Related managers (e.g. `user.projects`) are built from this class too,
    so reverse relations are tenant-scoped and fail closed the same way.
    """

    def get_queryset(self):
        org = _require_active_org(self.model)
        return super().get_queryset().filter(organization=org)


class TenantOwnedModel(models.Model):
    """Abstract base for every tenant-owned table.

    Adds the `organization` FK, auto-assigns it from the active tenant on
    create, and exposes two managers:
      - `objects` (TenantManager): the default; filtered to the active org,
        raises if none is active.
      - `all_tenants` (plain Manager): unfiltered, for admin/system use only.

    Write guards:
      - `organization` is immutable once the row exists.
      - While a tenant is active, rows of any other organization cannot be
        created, saved or deleted, whichever manager they were loaded from.
      - With no active tenant (system code), an explicit organization is
        required on create.
    """

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, editable=False
    )

    objects = TenantManager()
    all_tenants = models.Manager()

    class Meta:
        abstract = True

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._loaded_organization_id = instance.__dict__.get("organization_id")
        return instance

    def _assign_or_check_organization(self, org):
        if not self.organization_id:
            self.organization = org
        elif self.organization_id != org.id:
            raise TenantMismatchError(_mismatch_message(self, org))

    def save(self, *args, **kwargs):
        org = get_current_org()
        if self._state.adding:
            if org is not None:
                self._assign_or_check_organization(org)
            elif not self.organization_id:
                raise NoActiveTenantError(
                    f"Cannot create a {type(self).__name__} with no active "
                    "tenant and no explicit organization set."
                )
        else:
            loaded = getattr(self, "_loaded_organization_id", self.organization_id)
            if self.organization_id != loaded:
                raise TenantMismatchError("A row's organization cannot be changed.")
            if org is not None and self.organization_id != org.id:
                raise TenantMismatchError(_mismatch_message(self, org))
        super().save(*args, **kwargs)
        self._loaded_organization_id = self.organization_id

    def delete(self, *args, **kwargs):
        org = get_current_org()
        if org is not None and self.organization_id != org.id:
            raise TenantMismatchError(_mismatch_message(self, org))
        return super().delete(*args, **kwargs)


class _InvitationFilters:
    def pending(self):
        return self.filter(
            accepted_at__isnull=True, revoked_at__isnull=True, expires_at__gt=timezone.now()
        )


class InvitationQuerySet(_InvitationFilters, TenantQuerySet):
    pass


class AllTenantsInvitationQuerySet(_InvitationFilters, models.QuerySet):
    pass


class InvitationManager(TenantManager.from_queryset(InvitationQuerySet)):
    pass


class Invitation(TenantOwnedModel):
    """A single-use, expiring invitation to join an organization.

    Only a SHA-256 hash of the token is stored; the raw token exists only in
    the email sent to the invitee, so a database leak does not leak usable
    invitations.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        EXPIRED = "expired", "Expired"
        REVOKED = "revoked", "Revoked"

    email = models.EmailField()
    role = models.CharField(
        max_length=10, choices=Membership.Role.choices, default=Membership.Role.MEMBER
    )
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    revoked_at = models.DateTimeField(null=True, blank=True)

    objects = InvitationManager()
    all_tenants = models.Manager.from_queryset(AllTenantsInvitationQuerySet)()

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            # At most one open (not accepted, not revoked) invitation per
            # email per org. Expired ones are revoked before re-inviting.
            models.UniqueConstraint(
                fields=["organization", "email"],
                condition=models.Q(accepted_at__isnull=True, revoked_at__isnull=True),
                name="one_open_invitation_per_email",
            ),
        ]

    def __str__(self):
        return f"{self.email} -> {self.organization_id} ({self.role})"

    @staticmethod
    def hash_token(raw_token):
        return hashlib.sha256(raw_token.encode()).hexdigest()

    @classmethod
    def issue(cls, *, email, role, invited_by):
        """Create an invitation in the active tenant; return (invitation, raw_token)."""
        raw_token = secrets.token_urlsafe(32)
        invitation = cls.objects.create(
            email=email.lower(),
            role=role,
            invited_by=invited_by,
            token_hash=cls.hash_token(raw_token),
            expires_at=timezone.now() + timedelta(hours=settings.INVITATION_TTL_HOURS),
        )
        return invitation, raw_token

    @property
    def status(self):
        if self.accepted_at:
            return self.Status.ACCEPTED
        if self.revoked_at:
            return self.Status.REVOKED
        if self.expires_at <= timezone.now():
            return self.Status.EXPIRED
        return self.Status.PENDING
