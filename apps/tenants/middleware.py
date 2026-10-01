from django.http import JsonResponse

from apps.tenants.context import reset_current_org, set_current_org
from apps.tenants.models import Membership, Organization

TENANT_PATH_PREFIXES = ("/api/",)


class TenantMiddleware:
    """Resolves the active organization from the `X-Org` request header.

    For any request under a tenant-scoped path prefix:
      - Missing `X-Org` header -> 400.
      - `X-Org` does not match a known Organization -> 403 (doesn't reveal
        whether the slug exists).
      - Authenticated user has no Membership in that org -> 403.
      - Anonymous requests are let through unauthenticated; view-level
        permission classes (IsAuthenticated) are responsible for the 401.

    On success, the resolved Organization is stored in a contextvar for the
    duration of the request and reset afterwards, so it never leaks into a
    later request handled on the same thread/task.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith(TENANT_PATH_PREFIXES):
            return self.get_response(request)

        org_slug = request.headers.get("X-Org")
        if not org_slug:
            return JsonResponse(
                {"detail": "The X-Org header is required."}, status=400
            )

        try:
            org = Organization.objects.get(slug=org_slug)
        except Organization.DoesNotExist:
            return JsonResponse(
                {"detail": "Not a member of this organization."}, status=403
            )

        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            is_member = Membership.objects.filter(user=user, organization=org).exists()
            if not is_member:
                return JsonResponse(
                    {"detail": "Not a member of this organization."}, status=403
                )

        token = set_current_org(org)
        try:
            response = self.get_response(request)
        finally:
            reset_current_org(token)
        return response
