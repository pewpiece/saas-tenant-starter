class NoActiveTenantError(RuntimeError):
    """Raised when a tenant-scoped manager is used with no active organization.

    This is a programming-error signal, not a user-facing error: it means
    code queried a TenantOwnedModel's default manager outside of a tenant
    context (e.g. a shell, a management command, or a Celery task). Wrap
    that code in `tenant_context(org)`, or use the model's `all_tenants`
    manager for genuine cross-tenant admin/system access.
    """


class TenantMismatchError(RuntimeError):
    """Raised when a write would put a row in, or move it to, another tenant."""


class UnscopedQueryError(RuntimeError):
    """Raised for query APIs the tenant manager cannot scope (e.g. raw SQL).

    Use `Model.all_tenants` and filter on organization explicitly instead.
    """


class LastOwnerError(Exception):
    """Raised when a change would leave an organization without an owner."""
