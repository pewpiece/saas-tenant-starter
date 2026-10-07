"""D-10 coverage gaps: check what a request did to the database, not just its
status code, and cover writes through real Basic and session auth."""

import pytest

from apps.projects.models import Project
from apps.projects.tests.factories import ProjectFactory
from apps.tenants.models import Membership

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("method", ["patch", "put"])
def test_organization_in_body_is_ignored_on_update(basic_client, org_a, org_b, make_org_member, method):
    owner = make_org_member(org_a, role=Membership.Role.OWNER)
    project = ProjectFactory(organization=org_a)
    body = {"name": "moved?", "organization": org_b.slug, "organization_id": org_b.id}

    response = getattr(basic_client(owner, org_slug=org_a.slug), method)(
        f"/api/projects/{project.id}/", body, format="json"
    )

    assert response.status_code == 200
    assert Project.all_tenants.get(pk=project.pk).organization_id == org_a.id


def test_created_by_in_body_is_ignored(basic_client, org_a, make_org_member):
    owner = make_org_member(org_a, role=Membership.Role.OWNER)
    someone_else = make_org_member(org_a)

    response = basic_client(owner, org_slug=org_a.slug).post(
        "/api/projects/", {"name": "x", "created_by": someone_else.id}, format="json"
    )

    assert response.status_code == 201
    assert Project.all_tenants.get(pk=response.data["id"]).created_by_id == owner.id


def test_denied_update_leaves_row_unchanged(basic_client, org_a, make_org_member):
    member = make_org_member(org_a, role=Membership.Role.MEMBER)
    project = ProjectFactory(organization=org_a, name="original")

    response = basic_client(member, org_slug=org_a.slug).patch(
        f"/api/projects/{project.id}/", {"name": "hacked"}, format="json"
    )

    assert response.status_code == 403
    assert Project.all_tenants.get(pk=project.pk).name == "original"


def test_denied_delete_leaves_row_in_place(basic_client, org_a, make_org_member):
    admin = make_org_member(org_a, role=Membership.Role.ADMIN)
    project = ProjectFactory(organization=org_a)

    response = basic_client(admin, org_slug=org_a.slug).delete(f"/api/projects/{project.id}/")

    assert response.status_code == 403
    assert Project.all_tenants.filter(pk=project.pk).exists()


def test_cross_org_update_and_delete_leave_row_untouched(basic_client, org_a, org_b, make_org_member):
    owner_a = make_org_member(org_a, role=Membership.Role.OWNER)
    theirs = ProjectFactory(organization=org_b, name="theirs")
    client = basic_client(owner_a, org_slug=org_a.slug)

    patch = client.patch(f"/api/projects/{theirs.id}/", {"name": "pwned"}, format="json")
    delete = client.delete(f"/api/projects/{theirs.id}/")

    assert (patch.status_code, delete.status_code) == (404, 404)
    assert Project.all_tenants.get(pk=theirs.pk).name == "theirs"


def test_session_auth_write_requires_csrf_token(session_client, org_a, make_org_member):
    owner = make_org_member(org_a, role=Membership.Role.OWNER)
    client = session_client(owner, org_slug=org_a.slug, enforce_csrf_checks=True)

    response = client.post("/api/projects/", {"name": "x"}, format="json")

    assert response.status_code == 403
    assert "CSRF" in response.data["detail"]
    assert not Project.all_tenants.filter(name="x").exists()
