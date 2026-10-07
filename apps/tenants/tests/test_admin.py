"""D-06: the Django admin must be usable for cross-tenant support work."""

import pytest

from apps.accounts.models import User
from apps.projects.models import Project
from apps.projects.tests.factories import ProjectFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(client):
    superuser = User.objects.create_superuser("root@example.com", "rootpass-123")
    client.force_login(superuser)
    return client


@pytest.mark.parametrize(
    "path",
    ["accounts/user", "tenants/organization", "tenants/membership", "projects/project"],
)
def test_changelist_loads(admin_client, path):
    assert admin_client.get(f"/admin/{path}/").status_code == 200


def test_project_changelist_shows_every_org(admin_client, org_a, org_b):
    ProjectFactory(organization=org_a, name="alpha-project")
    ProjectFactory(organization=org_b, name="beta-project")

    content = admin_client.get("/admin/projects/project/").content

    assert b"alpha-project" in content
    assert b"beta-project" in content


def test_project_change_page_loads(admin_client, org_a):
    project = ProjectFactory(organization=org_a)

    response = admin_client.get(f"/admin/projects/project/{project.pk}/change/")

    assert response.status_code == 200


def test_project_can_be_created_for_a_chosen_org(admin_client, org_b):
    creator = ProjectFactory(organization=org_b).created_by

    response = admin_client.post(
        "/admin/projects/project/add/",
        {"organization": org_b.pk, "name": "made-in-admin", "description": "", "created_by": creator.pk},
    )

    assert response.status_code == 302, response.content[:2000]
    assert Project.all_tenants.get(name="made-in-admin").organization_id == org_b.id


def test_user_can_be_created_in_admin(admin_client):
    response = admin_client.post(
        "/admin/accounts/user/add/",
        {"email": "new@example.com", "password1": "Very-long-pass-42", "password2": "Very-long-pass-42"},
    )

    assert response.status_code == 302, response.content[:2000]
    assert User.objects.filter(email="new@example.com").exists()
