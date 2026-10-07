"""D-08: the API must scale per request and resist abuse."""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.throttling import SimpleRateThrottle

from apps.projects.tests.factories import ProjectFactory
from apps.tenants.models import Membership

pytestmark = pytest.mark.django_db


def test_tenant_resolution_uses_one_membership_query(session_client, org_a, make_org_member):
    user = make_org_member(org_a, role=Membership.Role.OWNER)
    client = session_client(user, org_slug=org_a.slug)

    with CaptureQueriesContext(connection) as ctx:
        response = client.get("/api/projects/")

    assert response.status_code == 200
    tenancy_queries = [
        q["sql"]
        for q in ctx.captured_queries
        if "tenants_membership" in q["sql"] or "tenants_organization" in q["sql"]
    ]
    assert len(tenancy_queries) == 1, tenancy_queries


def test_project_list_is_paginated(basic_client, org_a, make_org_member):
    user = make_org_member(org_a)
    ProjectFactory.create_batch(25, organization=org_a)

    response = basic_client(user, org_slug=org_a.slug).get("/api/projects/")

    assert response.status_code == 200
    assert response.data["count"] == 25
    assert len(response.data["results"]) == 20
    assert response.data["next"] is not None


def test_page_size_is_capped_at_100(basic_client, org_a, make_org_member):
    user = make_org_member(org_a)
    ProjectFactory.create_batch(101, organization=org_a, created_by=user)

    response = basic_client(user, org_slug=org_a.slug).get("/api/projects/?page_size=100000")

    assert response.status_code == 200
    assert response.data["count"] == 101
    assert len(response.data["results"]) == 100


def test_authenticated_requests_are_throttled(basic_client, org_a, make_org_member, monkeypatch):
    monkeypatch.setattr(SimpleRateThrottle, "THROTTLE_RATES", {"user": "3/min", "anon": "3/min"})
    client = basic_client(make_org_member(org_a), org_slug=org_a.slug)

    statuses = [client.get("/api/projects/").status_code for _ in range(4)]

    assert statuses == [200, 200, 200, 429]


def test_failed_basic_auth_attempts_are_throttled_per_ip(
    basic_client, org_a, make_org_member, settings
):
    settings.AUTH_FAILURE_LIMIT = 3
    user = make_org_member(org_a)
    bad = basic_client(user, org_slug=org_a.slug, password="wrong")
    good = basic_client(user, org_slug=org_a.slug)

    statuses = [bad.get("/api/projects/").status_code for _ in range(3)]
    locked = good.get("/api/projects/")
    other_ip = good.get("/api/projects/", REMOTE_ADDR="10.9.9.9")

    assert statuses == [401, 401, 401]
    assert locked.status_code == 429
    assert other_ip.status_code == 200
