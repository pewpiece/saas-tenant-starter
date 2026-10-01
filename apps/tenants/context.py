"""Request-scoped "current organization" state, backed by a contextvar.

Using a contextvar (rather than e.g. thread-locals) keeps this safe under
async views/ASGI, where multiple requests can interleave on the same thread.
"""

import contextvars

_current_org_var: contextvars.ContextVar = contextvars.ContextVar("current_org", default=None)


def get_current_org():
    """Return the Organization active for this request, or None."""
    return _current_org_var.get()


def set_current_org(org):
    """Set the active Organization and return a token for reset_current_org()."""
    return _current_org_var.set(org)


def reset_current_org(token):
    """Undo a set_current_org() call. Must be called with that call's token."""
    _current_org_var.reset(token)
