from rest_framework.exceptions import PermissionDenied


class PlanLimitReached(PermissionDenied):
    default_detail = "Your plan's limit has been reached. Upgrade to add more."
    default_code = "plan_limit_reached"


class FeatureNotInPlan(PermissionDenied):
    default_detail = "This feature requires the Pro plan."
    default_code = "plan_upgrade_required"
