class AppendOnlyError(RuntimeError):
    """Raised on any attempt to change or delete an audit log entry."""
