import base64

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from apps.tenants.models import Membership
from apps.tenants.tests.factories import MembershipFactory, OrganizationFactory


@pytest.fixture(autouse=True)
def _clear_cache():
    """Throttle counters live in the cache; never let them leak between tests."""
    cache.clear()
    yield
    cache.clear()


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


def basic_auth_header(email, password=DEFAULT_PASSWORD):
    token = base64.b64encode(f"{email}:{password}".encode()).decode()
    return f"Basic {token}"


@pytest.fixture
def basic_client():
    """An APIClient that authenticates with a real HTTP Basic header.

    Unlike force_authenticate, this goes through DRF's real authentication
    classes, so it exercises the same path a production client does.
    """

    def _make(user=None, org_slug=None, password=DEFAULT_PASSWORD, email=None):
        client = APIClient()
        creds = {}
        if user is not None or email is not None:
            creds["HTTP_AUTHORIZATION"] = basic_auth_header(email or user.email, password)
        if org_slug is not None:
            creds["HTTP_X_ORG"] = org_slug
        client.credentials(**creds)
        return client

    return _make


@pytest.fixture
def session_client():
    """An APIClient logged in through Django's real session machinery."""

    def _make(user, org_slug=None, password=DEFAULT_PASSWORD, enforce_csrf_checks=False):
        client = APIClient(enforce_csrf_checks=enforce_csrf_checks)
        assert client.login(email=user.email, password=password)
        if org_slug is not None:
            client.credentials(HTTP_X_ORG=org_slug)
        return client

    return _make


def authed_client(api_client, user, org_slug=None):
    """Authenticate `api_client` as `user` and, if given, set the X-Org header."""
    api_client.force_authenticate(user=user)
    if org_slug is not None:
        api_client.credentials(HTTP_X_ORG=org_slug)
    return api_client
