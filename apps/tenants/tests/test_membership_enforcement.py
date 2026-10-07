"""D-02: membership must be enforced for every auth method, in one shared layer.

Under Milestone 1 the middleware's membership check never ran for HTTP Basic
requests (DRF authenticates later, inside the view), so only
ProjectRolePermission stood between a non-member and the org's data. These
tests simulate a future tenant view that forgets that permission class by
neutralising it, and check that a non-member is still refused.
"""

import pytest

from apps.projects.permissions import ProjectRolePermission
from apps.projects.tests.factories import ProjectFactory
from apps.tenants.context import get_current_org

pytestmark = pytest.mark.django_db


@pytest.fixture
def role_check_removed(monkeypatch):
    monkeypatch.setattr(ProjectRolePermission, "has_permission", lambda self, request, view: True)


def test_basic_auth_nonmember_refused_even_without_role_permission(
    basic_client, org_a, org_b, make_org_member, role_check_removed
):
    ProjectFactory(organization=org_a, name="acme-secret-roadmap")
    outsider = make_org_member(org_b)

    response = basic_client(outsider, org_slug=org_a.slug).get("/api/projects/")

    assert response.status_code == 403
    assert b"acme-secret-roadmap" not in response.content


def test_session_auth_nonmember_refused_even_without_role_permission(
    session_client, org_a, org_b, make_org_member, role_check_removed
):
    ProjectFactory(organization=org_a, name="acme-secret-roadmap")
    outsider = make_org_member(org_b)

    response = session_client(outsider, org_slug=org_a.slug).get("/api/projects/")

    assert response.status_code == 403
    assert b"acme-secret-roadmap" not in response.content


def test_tenant_context_never_set_for_nonmember(
    basic_client, org_a, org_b, make_org_member, monkeypatch
):
    seen = []
    original = ProjectRolePermission.has_permission

    def spy(self, request, view):
        seen.append(get_current_org())
        return original(self, request, view)

    monkeypatch.setattr(ProjectRolePermission, "has_permission", spy)
    outsider = make_org_member(org_b)

    basic_client(outsider, org_slug=org_a.slug).get("/api/projects/")

    assert org_a not in seen
