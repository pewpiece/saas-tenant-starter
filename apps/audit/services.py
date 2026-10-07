from apps.audit.models import AuditLogEntry


def record(action, *, actor=None, target=None, changes=None):
    """Append an audit entry to the active tenant's log.

    Must run with a tenant active (inside a tenant-scoped request or
    tenant_context); the entry's organization comes from it.
    """
    if actor is not None and not getattr(actor, "is_authenticated", False):
        actor = None
    return AuditLogEntry.objects.create(
        action=action,
        actor=actor,
        actor_email=getattr(actor, "email", "") or "",
        target_type=target._meta.label_lower if target is not None else "",
        target_id=str(target.pk) if target is not None else "",
        target_repr=str(target)[:255] if target is not None else "",
        changes=changes or {},
    )


def diff(instance, old_values, fields):
    """Return {field: [old, new]} for the fields whose value changed."""
    changes = {}
    for field in fields:
        new = getattr(instance, field)
        if old_values.get(field) != new:
            changes[field] = [old_values.get(field), new]
    return changes
