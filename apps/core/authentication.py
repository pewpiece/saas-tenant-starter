from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from rest_framework.authentication import (
    BaseAuthentication,
    BasicAuthentication,
    get_authorization_header,
)
from rest_framework.exceptions import AuthenticationFailed, Throttled
from rest_framework.throttling import BaseThrottle


def _failure_key(request):
    return f"auth-failures:{BaseThrottle().get_ident(request)}"


def ensure_not_locked_out(request):
    """Raise Throttled (429) if this client IP has too many recent failures."""
    if cache.get(_failure_key(request), 0) >= settings.AUTH_FAILURE_LIMIT:
        raise Throttled(wait=settings.AUTH_FAILURE_WINDOW)


def record_auth_failure(request):
    key = _failure_key(request)
    if not cache.add(key, 1, timeout=settings.AUTH_FAILURE_WINDOW):
        cache.incr(key)


class ThrottledBasicAuthentication(BasicAuthentication):
    """HTTP Basic auth that locks out a client IP after repeated failures.

    DRF throttles run after authentication, so a failed password never
    reaches them: without this, Basic auth could be brute-forced at full
    speed. After AUTH_FAILURE_LIMIT failures within AUTH_FAILURE_WINDOW
    seconds, every request from that IP gets 429 until the window expires.

    Counters live in the default cache, so they are per process with the
    default LocMemCache; production needs a shared cache (e.g. Redis).
    """

    def authenticate(self, request):
        ensure_not_locked_out(request)
        try:
            return super().authenticate(request)
        except AuthenticationFailed:
            record_auth_failure(request)
            raise


class BearerTokenAuthentication(BaseAuthentication):
    """`Authorization: Bearer <token>` with a token from POST /api/auth/token/.

    Unlike Basic auth this costs one indexed lookup per request, not a
    password hash (D-18). request.auth is the AuthToken row.
    """

    keyword = b"bearer"

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts or parts[0].lower() != self.keyword:
            return None
        if len(parts) != 2:
            raise AuthenticationFailed("Invalid token header.")
        try:
            key = parts[1].decode()
        except UnicodeError:
            raise AuthenticationFailed("Invalid token header.") from None

        from apps.accounts.models import AuthToken

        token = AuthToken.objects.select_related("user").filter(key_hash=AuthToken.hash_key(key)).first()
        if token is None or token.expires_at <= timezone.now() or not token.user.is_active:
            raise AuthenticationFailed("Invalid or expired token.")
        return token.user, token

    def authenticate_header(self, request):
        return "Bearer"
