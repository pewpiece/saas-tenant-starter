CDN = "https://cdn.jsdelivr.net"

# JSON responses never render anything, so the API gets the strictest policy.
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"

# The admin serves all its assets itself; it needs inline styles (widgets) but
# no inline or remote scripts.
ADMIN_CSP = (
    "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"
)

# Swagger UI loads its bundle from a CDN and starts itself from an inline
# script, so this page (and only this page) allows both.
DOCS_CSP = (
    f"default-src 'self'; script-src 'self' 'unsafe-inline' {CDN}; "
    f"style-src 'self' 'unsafe-inline' {CDN}; img-src 'self' data: {CDN}; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"
)

PERMISSIONS_POLICY = "accelerometer=(), camera=(), geolocation=(), gyroscope=(), microphone=(), payment=(), usb=()"


class SecurityHeadersMiddleware:
    """Adds CSP, Permissions-Policy and COEP headers (D-20).

    Django's SecurityMiddleware already covers HSTS, nosniff, Referrer-Policy
    and Cross-Origin-Opener-Policy; X-Frame-Options comes from
    XFrameOptionsMiddleware. A view that sets one of these headers itself
    wins (setdefault).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.headers.setdefault("Content-Security-Policy", self._csp_for(request.path))
        response.headers.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
        # credentialless (not require-corp) so the Swagger UI's CDN assets keep loading.
        response.headers.setdefault("Cross-Origin-Embedder-Policy", "credentialless")
        return response

    @staticmethod
    def _csp_for(path):
        if path.startswith("/api/docs/"):
            return DOCS_CSP
        if path.startswith("/admin/") or not path.startswith("/api/"):
            return ADMIN_CSP
        return API_CSP
