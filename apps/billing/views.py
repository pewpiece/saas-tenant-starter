from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record
from apps.billing.serializers import ChangePlanSerializer, SubscriptionSerializer
from apps.billing.services import get_subscription, lock_organization, over_limit, usage
from apps.tenants.models import Membership
from apps.tenants.permissions import has_role
from apps.tenants.views import TenantScopedViewMixin


def _describe(subscription, org):
    limits = subscription.limits
    exceeded = over_limit(org, subscription)
    warnings = []
    if exceeded["projects"]:
        warnings.append(
            f"This organization has more projects than the {subscription.plan} plan allows "
            f"({limits.max_projects}). Existing projects stay available; new projects are "
            "blocked until you are under the limit or upgrade."
        )
    if exceeded["members"]:
        warnings.append(
            f"This organization has more members than the {subscription.plan} plan allows "
            f"({limits.max_members}). Existing members keep access; new members are blocked "
            "until you are under the limit or upgrade."
        )
    return {
        "plan": subscription.plan,
        "limits": {
            "max_members": limits.max_members,
            "max_projects": limits.max_projects,
            "features": sorted(limits.features),
        },
        "usage": usage(org),
        "over_limit": exceeded,
        "warnings": warnings,
    }


class SubscriptionView(TenantScopedViewMixin, APIView):
    """The active organization's plan (mock billing, no payment provider).

    Every member can view it; only owners change it. Downgrading is allowed
    even when the org is over the new plan's limits: nothing is deleted, but
    adding projects or members is blocked until usage is back under the limit.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=SubscriptionSerializer)
    def get(self, request):
        return Response(_describe(get_subscription(request.tenant), request.tenant))

    @extend_schema(request=ChangePlanSerializer, responses=SubscriptionSerializer)
    def patch(self, request):
        if not has_role(request, Membership.Role.OWNER):
            self.permission_denied(request, message="Only an owner can change the plan.")
        serializer = ChangePlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lock_organization(request.tenant)
        subscription = get_subscription(request.tenant)
        old_plan, new_plan = subscription.plan, serializer.validated_data["plan"]
        if new_plan != old_plan:
            subscription.plan = new_plan
            subscription.save(update_fields=["plan", "updated_at"])
            record(
                "subscription.change",
                actor=request.user,
                target=subscription,
                changes={"plan": [old_plan, new_plan]},
            )
        return Response(_describe(subscription, request.tenant))
