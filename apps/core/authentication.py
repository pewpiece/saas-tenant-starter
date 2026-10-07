from django.conf import settings
from django.core.cache import cache
from rest_framework.authentication import BasicAuthentication
from rest_framework.exceptions import AuthenticationFailed, Throttled
from rest_framework.throttling import BaseThrottle


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
        key = f"auth-failures:{BaseThrottle().get_ident(request)}"
        window = settings.AUTH_FAILURE_WINDOW
        if cache.get(key, 0) >= settings.AUTH_FAILURE_LIMIT:
            raise Throttled(wait=window)
        try:
            return super().authenticate(request)
        except AuthenticationFailed:
            if not cache.add(key, 1, timeout=window):
                cache.incr(key)
            raise
