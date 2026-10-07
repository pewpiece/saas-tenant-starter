from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.tenants.models import Membership


class ProjectRolePermission(BasePermission):
    """Role matrix for /api/projects/.

    - member/admin/owner: list, retrieve
    - admin, owner: create, update
    - owner only: delete

    Relies on TenantScopedViewMixin having already resolved the caller's
    membership in the active organization.
    """

    message = "You do not have permission to perform this action in this organization."

    def has_permission(self, request, view):
        membership = getattr(request, "membership", None)
        if membership is None:
            return False

        if request.method in SAFE_METHODS:
            return True

        if view.action == "destroy":
            return membership.role == Membership.Role.OWNER

        return membership.role in (Membership.Role.OWNER, Membership.Role.ADMIN)
