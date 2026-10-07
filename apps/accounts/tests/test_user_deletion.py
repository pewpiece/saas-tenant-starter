"""D-07: deleting a user must not destroy other tenants' data or orphan an org."""

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.projects.models import Project
from apps.projects.tests.factories import ProjectFactory
from apps.tenants import exceptions
from apps.tenants.models import Membership
from apps.tenants.tests.factories import MembershipFactory

pytestmark = pytest.mark.django_db

OWNER = Membership.Role.OWNER
ADMIN = Membership.Role.ADMIN


def test_deleting_user_keeps_projects_they_created_in_every_org(org_a, org_b):
    leaver = UserFactory()
    for org in (org_a, org_b):
        MembershipFactory(organization=org, role=OWNER)
        MembershipFactory(user=leaver, organization=org, role=ADMIN)
    in_a = ProjectFactory(organization=org_a, created_by=leaver)
    in_b = ProjectFactory(organization=org_b, created_by=leaver)

    leaver.delete()

    kept = Project.all_tenants.filter(pk__in=[in_a.pk, in_b.pk])
    assert kept.count() == 2
    assert all(p.created_by_id is None for p in kept)


def test_deleting_sole_owner_of_an_org_is_blocked(org_a):
    owner = UserFactory()
    MembershipFactory(user=owner, organization=org_a, role=OWNER)

    with pytest.raises(exceptions.LastOwnerError):
        owner.delete()

    assert type(owner).objects.filter(pk=owner.pk).exists()


def test_deleting_one_of_two_owners_is_allowed(org_a):
    owner = UserFactory()
    MembershipFactory(user=owner, organization=org_a, role=OWNER)
    MembershipFactory(organization=org_a, role=OWNER)

    owner.delete()

    assert Membership.objects.filter(organization=org_a, role=OWNER).count() == 1


def test_removing_last_owner_membership_is_blocked(org_a):
    membership = MembershipFactory(organization=org_a, role=OWNER)

    with pytest.raises(exceptions.LastOwnerError):
        membership.delete()

    assert Membership.objects.filter(pk=membership.pk).exists()


def test_demoting_last_owner_is_blocked(org_a):
    membership = MembershipFactory(organization=org_a, role=OWNER)

    membership.role = ADMIN
    with pytest.raises(exceptions.LastOwnerError):
        membership.save()

    assert Membership.objects.get(pk=membership.pk).role == OWNER


def test_demoting_owner_when_another_owner_exists_is_allowed(org_a):
    membership = MembershipFactory(organization=org_a, role=OWNER)
    MembershipFactory(organization=org_a, role=OWNER)

    membership.role = ADMIN
    membership.save()

    assert Membership.objects.get(pk=membership.pk).role == ADMIN


def test_deleting_an_org_still_cascades_its_memberships(org_a):
    MembershipFactory(organization=org_a, role=OWNER)

    org_a.delete()

    assert not Membership.objects.filter(organization_id=org_a.pk).exists()
