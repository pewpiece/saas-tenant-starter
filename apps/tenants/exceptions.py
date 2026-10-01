class NoActiveTenantError(RuntimeError):
    """Raised when a tenant-scoped manager is used with no active organization.

    This is a programming-error signal, not a user-facing error: it means
    code queried a TenantOwnedModel's default manager outside of a request
    that went through TenantMiddleware (e.g. a shell, a management command,
    or a Celery task). Use the model's `all_tenants` manager for that kind
    of admin/system access instead of catching this.
    """
