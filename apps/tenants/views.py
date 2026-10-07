from rest_framework.exceptions import NotAuthenticated, ParseError, PermissionDenied

from apps.tenants.context import reset_current_org, set_current_org
from apps.tenants.models import Membership

TENANT_HEADER = "X-Org"


class NotAMember(PermissionDenied):
    # One message for "slug does not exist" and "you are not a member", so
    # the response never reveals which organizations exist.
    default_detail = "You are not a member of this organization."
    default_code = "not_a_member"


class TenantScopedViewMixin:
    """Resolves the active organization for a DRF view from the X-Org header.

    Every tenant-scoped view must use this mixin. It runs after DRF
    authentication and before the view's permission classes, so it sees the
    real user whatever the auth method (Basic, session, ...):

      - unauthenticated              -> 401 with a WWW-Authenticate challenge
      - missing X-Org header         -> 400
      - unknown slug or non-member   -> 403, byte-identical in both cases

    On success it sets `request.tenant` and `request.membership` and
    activates the tenant context for the rest of the request, resetting it
    when the request finishes, even if the view raised.
    """

    _tenant_token = None

    def tenant_queryset(self, queryset_factory, empty_queryset):
        """Return queryset_factory(), or an empty queryset during schema generation.

        drf-spectacular introspects views without a request or tenant, where
        the tenant-scoped managers (correctly) raise.
        """
        if getattr(self, "swagger_fake_view", False):
            return empty_queryset
        return queryset_factory()

    def check_permissions(self, request):
        # DRF's initial() authenticates, then calls check_permissions(), so
        # this is the first point where request.user is reliable.
        self.resolve_tenant(request)
        super().check_permissions(request)

    def resolve_tenant(self, request):
        if not (request.user and request.user.is_authenticated):
            raise NotAuthenticated()

        slug = request.headers.get(TENANT_HEADER)
        if not slug:
            raise ParseError(f"The {TENANT_HEADER} header is required.")

        membership = (
            Membership.objects.select_related("organization")
            .filter(user=request.user, organization__slug=slug)
            .first()
        )
        if membership is None:
            raise NotAMember()

        request.tenant = membership.organization
        request.membership = membership
        self._tenant_token = set_current_org(membership.organization)

    def dispatch(self, request, *args, **kwargs):
        try:
            return super().dispatch(request, *args, **kwargs)
        finally:
            if self._tenant_token is not None:
                reset_current_org(self._tenant_token)
                self._tenant_token = None
