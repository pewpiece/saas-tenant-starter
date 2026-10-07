from apps.billing.exceptions import FeatureNotInPlan, PlanLimitReached
from apps.billing.models import Subscription
from apps.tenants.models import Membership, Organization


def get_subscription(org):
    subscription, _ = Subscription.objects.get_or_create(organization=org)
    return subscription


def lock_organization(org):
    """Serialise limit checks per org (call inside a transaction).

    Without this, two concurrent requests at the limit could both pass the
    count check and both create a row.
    """
    Organization.objects.select_for_update().filter(pk=org.pk).first()


def usage(org):
    from apps.projects.models import Project
    from apps.tenants.models import Invitation

    return {
        "members": Membership.objects.filter(organization=org).count(),
        "pending_invitations": Invitation.all_tenants.pending().filter(organization=org).count(),
        "projects": Project.all_tenants.filter(organization=org).count(),
    }


def over_limit(org, subscription=None):
    """Which limits the org currently exceeds (possible after a downgrade)."""
    limits = (subscription or get_subscription(org)).limits
    current = usage(org)
    return {
        "members": limits.max_members is not None and current["members"] > limits.max_members,
        "projects": limits.max_projects is not None and current["projects"] > limits.max_projects,
    }


def ensure_can_add_project(org):
    limit = get_subscription(org).limits.max_projects
    if limit is None:
        return
    from apps.projects.models import Project

    if Project.all_tenants.filter(organization=org).count() >= limit:
        raise PlanLimitReached(f"Your plan allows {limit} projects. Upgrade to add more.")


def ensure_can_add_member(org, *, count_pending_invitations):
    """Members (plus pending invitations, when inviting) must stay within the limit."""
    limit = get_subscription(org).limits.max_members
    if limit is None:
        return
    current = usage(org)
    seats = current["members"] + (current["pending_invitations"] if count_pending_invitations else 0)
    if seats >= limit:
        raise PlanLimitReached(f"Your plan allows {limit} members. Upgrade to add more.")


def ensure_feature(org, feature):
    if feature not in get_subscription(org).limits.features:
        raise FeatureNotInPlan()
