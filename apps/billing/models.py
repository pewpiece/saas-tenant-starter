from django.db import models

from apps.billing.plans import LIMITS, Plan
from apps.tenants.models import Organization


class Subscription(models.Model):
    """Mock subscription: the plan an organization is on. No payment provider.

    One row per organization (created with the org; created lazily as Free
    for orgs that predate billing). Not a TenantOwnedModel: it is looked up
    by organization explicitly, like Membership.
    """

    organization = models.OneToOneField(
        Organization, on_delete=models.CASCADE, related_name="subscription"
    )
    plan = models.CharField(max_length=10, choices=Plan.choices, default=Plan.FREE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.organization} ({self.plan})"

    @property
    def limits(self):
        return LIMITS[self.plan]
