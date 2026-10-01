import pytest

from apps.tenants.models import Membership

pytestmark = pytest.mark.django_db


def test_organization_in_body_is_ignored_on_create(api_client, org_a, org_b, make_org_member):
    owner = make_org_member(org_a, role=Membership.Role.OWNER)

    api_client.force_authenticate(user=owner)
    api_client.credentials(HTTP_X_ORG=org_a.slug)

    response = api_client.post(
        "/api/projects/",
        {"name": "Sneaky", "organization": org_b.slug, "organization_id": org_b.id},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["organization"] == org_a.slug
