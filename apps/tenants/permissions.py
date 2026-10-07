from rest_framework.permissions import BasePermission

from apps.tenants.models import Membership

ROLE_RANK = {
    Membership.Role.MEMBER: 0,
    Membership.Role.ADMIN: 1,
    Membership.Role.OWNER: 2,
}


def has_role(request, minimum):
    membership = getattr(request, "membership", None)
    return membership is not None and ROLE_RANK[membership.role] >= ROLE_RANK[minimum]


class IsTenantAdmin(BasePermission):
    """Admins and owners of the active organization."""

    message = "You do not have permission to perform this action in this organization."

    def has_permission(self, request, view):
        return has_role(request, Membership.Role.ADMIN)

