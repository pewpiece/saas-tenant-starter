from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.tenants.context import get_current_org
from apps.tenants.models import Membership


class ProjectRolePermission(BasePermission):
    """Role matrix for /api/projects/.

    - member/admin/owner: list, retrieve
    - admin, owner: create, update
    - owner only: delete
    """

    message = "You do not have permission to perform this action in this organization."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        org = get_current_org()
        if org is None:
            return False

        try:
            role = Membership.objects.get(user=request.user, organization=org).role
        except Membership.DoesNotExist:
            return False

        if request.method in SAFE_METHODS:
            return True

        if view.action == "destroy":
            return role == Membership.Role.OWNER

        return role in (Membership.Role.OWNER, Membership.Role.ADMIN)
