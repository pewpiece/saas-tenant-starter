"""A user in several organizations switches between them with X-Org."""

import pytest

from apps.projects.tests.factories import ProjectFactory
from apps.tenants.context import get_current_org
from apps.tenants.models import Membership

pytestmark = pytest.mark.django_db


@pytest.fixture
def two_org_user(org_a, org_b, make_org_member):
    user = make_org_member(org_a, role=Membership.Role.OWNER)
    make_org_member(org_b, role=Membership.Role.MEMBER, user=user)
    ProjectFactory(organization=org_a, name="a-project")
    ProjectFactory(organization=org_b, name="b-project")
    return user


def _names(response):
    return {row["name"] for row in response.data["results"]}


def test_same_client_sees_each_org_only_under_its_header(basic_client, two_org_user):
    client = basic_client(two_org_user)

    in_a = client.get("/api/projects/", HTTP_X_ORG="org-a")
    in_b = client.get("/api/projects/", HTTP_X_ORG="org-b")
    in_a_again = client.get("/api/projects/", HTTP_X_ORG="org-a")

    assert _names(in_a) == _names(in_a_again) == {"a-project"}
    assert _names(in_b) == {"b-project"}
    assert get_current_org() is None


def test_role_is_per_org(basic_client, two_org_user):
    client = basic_client(two_org_user)

    as_owner = client.post("/api/projects/", {"name": "x"}, format="json", HTTP_X_ORG="org-a")
    as_member = client.post("/api/projects/", {"name": "y"}, format="json", HTTP_X_ORG="org-b")

    assert (as_owner.status_code, as_member.status_code) == (201, 403)
    assert as_owner.data["organization"] == "org-a"


def test_object_from_one_org_is_404_under_the_other(basic_client, two_org_user, org_a):
    project_a = ProjectFactory(organization=org_a)

    response = basic_client(two_org_user, org_slug="org-b").get(f"/api/projects/{project_a.id}/")

    assert response.status_code == 404


def test_session_user_switches_orgs_too(session_client, two_org_user):
    client = session_client(two_org_user)

    assert _names(client.get("/api/projects/", HTTP_X_ORG="org-a")) == {"a-project"}
    assert _names(client.get("/api/projects/", HTTP_X_ORG="org-b")) == {"b-project"}


def test_me_lists_both_orgs_with_their_roles(basic_client, two_org_user):
    orgs = basic_client(two_org_user).get("/api/me/").data["organizations"]

    assert {(o["slug"], o["role"]) for o in orgs} == {("org-a", "owner"), ("org-b", "member")}
