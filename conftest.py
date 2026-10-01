import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.tenants.models import Membership
from apps.tenants.tests.factories import MembershipFactory, OrganizationFactory


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def make_org_member():
    """Create a user who is a member of `org` with the given `role`."""

    def _make(org, role=Membership.Role.MEMBER, user=None):
        user = user or UserFactory()
        MembershipFactory(user=user, organization=org, role=role)
        return user

    return _make


@pytest.fixture
def org_a():
    return OrganizationFactory(name="Org A", slug="org-a")


@pytest.fixture
def org_b():
    return OrganizationFactory(name="Org B", slug="org-b")


def authed_client(api_client, user, org_slug=None):
    """Authenticate `api_client` as `user` and, if given, set the X-Org header."""
    api_client.force_authenticate(user=user)
    if org_slug is not None:
        api_client.credentials(HTTP_X_ORG=org_slug)
    return api_client
