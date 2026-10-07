from django.db import transaction

from apps.tenants.models import Membership, Organization


@transaction.atomic
def create_organization(*, name, slug, owner):
    """Create an organization with `owner` as its first owner, on the Free plan."""
    from apps.audit.services import record
    from apps.billing.models import Subscription
    from apps.tenants.context import tenant_context

    org = Organization.objects.create(name=name, slug=slug)
    Membership.objects.create(user=owner, organization=org, role=Membership.Role.OWNER)
    Subscription.objects.create(organization=org)
    with tenant_context(org):
        record("organization.create", actor=owner, target=org, changes={"name": name, "slug": slug})
    return org
