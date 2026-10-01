import pytest

from apps.projects.tests.factories import ProjectFactory
from apps.tenants.models import Membership

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "role, expected_status",
    [
        (Membership.Role.MEMBER, 200),
        (Membership.Role.ADMIN, 200),
        (Membership.Role.OWNER, 200),
    ],
)
def test_list(api_client, org_a, make_org_member, role, expected_status):
    user = make_org_member(org_a, role=role)
    ProjectFactory(organization=org_a)
    api_client.force_authenticate(user=user)
    api_client.credentials(HTTP_X_ORG=org_a.slug)

    response = api_client.get("/api/projects/")

    assert response.status_code == expected_status


@pytest.mark.parametrize(
    "role, expected_status",
    [
        (Membership.Role.MEMBER, 200),
        (Membership.Role.ADMIN, 200),
        (Membership.Role.OWNER, 200),
    ],
)
def test_retrieve(api_client, org_a, make_org_member, role, expected_status):
    user = make_org_member(org_a, role=role)
    project = ProjectFactory(organization=org_a)
    api_client.force_authenticate(user=user)
    api_client.credentials(HTTP_X_ORG=org_a.slug)

    response = api_client.get(f"/api/projects/{project.id}/")

    assert response.status_code == expected_status


@pytest.mark.parametrize(
    "role, expected_status",
    [
        (Membership.Role.MEMBER, 403),
        (Membership.Role.ADMIN, 201),
        (Membership.Role.OWNER, 201),
    ],
)
def test_create(api_client, org_a, make_org_member, role, expected_status):
    user = make_org_member(org_a, role=role)
    api_client.force_authenticate(user=user)
    api_client.credentials(HTTP_X_ORG=org_a.slug)

    response = api_client.post("/api/projects/", {"name": "New Project"}, format="json")

    assert response.status_code == expected_status


@pytest.mark.parametrize(
    "role, expected_status",
    [
        (Membership.Role.MEMBER, 403),
        (Membership.Role.ADMIN, 200),
        (Membership.Role.OWNER, 200),
    ],
)
def test_update(api_client, org_a, make_org_member, role, expected_status):
    user = make_org_member(org_a, role=role)
    project = ProjectFactory(organization=org_a)
    api_client.force_authenticate(user=user)
    api_client.credentials(HTTP_X_ORG=org_a.slug)

    response = api_client.patch(
        f"/api/projects/{project.id}/", {"name": "Renamed"}, format="json"
    )

    assert response.status_code == expected_status


@pytest.mark.parametrize(
    "role, expected_status",
    [
        (Membership.Role.MEMBER, 403),
        (Membership.Role.ADMIN, 403),
        (Membership.Role.OWNER, 204),
    ],
)
def test_delete(api_client, org_a, make_org_member, role, expected_status):
    user = make_org_member(org_a, role=role)
    project = ProjectFactory(organization=org_a)
    api_client.force_authenticate(user=user)
    api_client.credentials(HTTP_X_ORG=org_a.slug)

    response = api_client.delete(f"/api/projects/{project.id}/")

    assert response.status_code == expected_status
