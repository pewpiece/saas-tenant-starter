import pytest

from apps.projects.tests.factories import ProjectFactory
from apps.tenants.models import Membership

pytestmark = pytest.mark.django_db


def test_cross_org_detail_returns_404(api_client, org_a, org_b, make_org_member):
    user_a = make_org_member(org_a, role=Membership.Role.MEMBER)
    project_b = ProjectFactory(organization=org_b)

    api_client.force_authenticate(user=user_a)
    api_client.credentials(HTTP_X_ORG=org_a.slug)

    response = api_client.get(f"/api/projects/{project_b.id}/")

    assert response.status_code == 404


def test_list_never_includes_other_org_rows(api_client, org_a, org_b, make_org_member):
    user_a = make_org_member(org_a, role=Membership.Role.MEMBER)
    project_a = ProjectFactory(organization=org_a)
    ProjectFactory(organization=org_b)
    ProjectFactory(organization=org_b)

    api_client.force_authenticate(user=user_a)
    api_client.credentials(HTTP_X_ORG=org_a.slug)

    response = api_client.get("/api/projects/")

    assert response.status_code == 200
    returned_ids = {row["id"] for row in response.data}
    assert returned_ids == {project_a.id}
