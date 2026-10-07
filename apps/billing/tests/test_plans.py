import csv
import io

import pytest

from apps.audit.models import AuditLogEntry
from apps.billing.models import Subscription
from apps.projects.models import Project
from apps.projects.tests.factories import ProjectFactory
from apps.tenants.models import Membership

pytestmark = pytest.mark.django_db

OWNER, ADMIN, MEMBER = Membership.Role.OWNER, Membership.Role.ADMIN, Membership.Role.MEMBER


def set_plan(org, plan):
    Subscription.objects.update_or_create(organization=org, defaults={"plan": plan})


@pytest.fixture
def owner(org_a, make_org_member):
    return make_org_member(org_a, role=OWNER)


@pytest.fixture
def client(basic_client, owner, org_a):
    return basic_client(owner, org_slug=org_a.slug)


def create_project(client, name="p"):
    return client.post("/api/projects/", {"name": name}, format="json")


# --- project limit: Free = 5 ---------------------------------------------------------


@pytest.mark.parametrize("existing, expected", [(0, 201), (4, 201), (5, 403), (6, 403)])
def test_free_project_limit_boundary(client, org_a, owner, existing, expected):
    ProjectFactory.create_batch(existing, organization=org_a, created_by=owner)

    response = create_project(client)

    assert response.status_code == expected
    if expected == 403:
        assert response.data["detail"].code == "plan_limit_reached"
        assert Project.all_tenants.filter(organization=org_a).count() == existing


def test_pro_has_no_project_limit(client, org_a, owner):
    set_plan(org_a, "pro")
    ProjectFactory.create_batch(5, organization=org_a, created_by=owner)

    assert create_project(client).status_code == 201


def test_project_limit_is_per_org(client, org_a, org_b, owner):
    ProjectFactory.create_batch(5, organization=org_b)

    assert create_project(client).status_code == 201


def test_upgrade_unblocks_creation(client, org_a, owner):
    ProjectFactory.create_batch(5, organization=org_a, created_by=owner)
    assert create_project(client).status_code == 403

    client.patch("/api/subscription/", {"plan": "pro"}, format="json")

    assert create_project(client).status_code == 201


# --- downgrade with over-limit data -----------------------------------------------------


def test_downgrade_over_limit_keeps_data_and_warns(client, org_a, owner):
    set_plan(org_a, "pro")
    ProjectFactory.create_batch(7, organization=org_a, created_by=owner)

    response = client.patch("/api/subscription/", {"plan": "free"}, format="json")

    assert response.status_code == 200
    assert response.data["plan"] == "free"
    assert response.data["over_limit"] == {"members": False, "projects": True}
    assert response.data["usage"]["projects"] == 7
    assert len(response.data["warnings"]) == 1
    assert client.get("/api/projects/").data["count"] == 7


def test_over_limit_org_can_edit_and_delete_but_not_create(client, org_a, owner):
    set_plan(org_a, "pro")
    projects = ProjectFactory.create_batch(7, organization=org_a, created_by=owner)
    client.patch("/api/subscription/", {"plan": "free"}, format="json")

    edit = client.patch(f"/api/projects/{projects[0].id}/", {"name": "renamed"}, format="json")
    delete = client.delete(f"/api/projects/{projects[1].id}/")
    create = create_project(client)

    assert (edit.status_code, delete.status_code, create.status_code) == (200, 204, 403)


def test_creation_resumes_once_back_under_the_limit(client, org_a, owner):
    set_plan(org_a, "pro")
    projects = ProjectFactory.create_batch(6, organization=org_a, created_by=owner)
    client.patch("/api/subscription/", {"plan": "free"}, format="json")

    client.delete(f"/api/projects/{projects[0].id}/")  # 5: at the limit, still blocked
    at_limit = create_project(client)
    client.delete(f"/api/projects/{projects[1].id}/")  # 4: under the limit
    under = create_project(client)

    assert (at_limit.status_code, under.status_code) == (403, 201)


def test_downgrade_with_too_many_members_keeps_their_access(
    basic_client, client, org_a, make_org_member
):
    set_plan(org_a, "pro")
    extra = [make_org_member(org_a) for _ in range(4)]  # 5 members

    response = client.patch("/api/subscription/", {"plan": "free"}, format="json")
    invite = client.post("/api/invitations/", {"email": "new@example.com"}, format="json")

    assert response.data["over_limit"]["members"] is True
    assert invite.status_code == 403
    assert basic_client(extra[-1], org_slug=org_a.slug).get("/api/projects/").status_code == 200


# --- subscription endpoint --------------------------------------------------------------


@pytest.mark.parametrize("role", [OWNER, ADMIN, MEMBER])
def test_every_member_can_view_the_plan(basic_client, org_a, make_org_member, role):
    user = make_org_member(org_a, role=role)

    response = basic_client(user, org_slug=org_a.slug).get("/api/subscription/")

    assert response.status_code == 200
    assert response.data["plan"] == "free"
    assert response.data["limits"] == {"max_members": 3, "max_projects": 5, "features": []}


@pytest.mark.parametrize("role", [ADMIN, MEMBER])
def test_only_owner_changes_the_plan(basic_client, org_a, make_org_member, role):
    user = make_org_member(org_a, role=role)

    response = basic_client(user, org_slug=org_a.slug).patch(
        "/api/subscription/", {"plan": "pro"}, format="json"
    )

    assert response.status_code == 403
    assert not Subscription.objects.filter(organization=org_a, plan="pro").exists()


def test_plan_change_is_audited(client, org_a):
    client.patch("/api/subscription/", {"plan": "pro"}, format="json")

    entry = AuditLogEntry.all_tenants.get(organization=org_a, action="subscription.change")
    assert entry.changes == {"plan": ["free", "pro"]}


def test_unknown_plan_is_rejected(client, org_a):
    response = client.patch("/api/subscription/", {"plan": "enterprise"}, format="json")

    assert response.status_code == 400


def test_org_without_subscription_row_is_free(client, org_a):
    Subscription.objects.filter(organization=org_a).delete()

    assert client.get("/api/subscription/").data["plan"] == "free"


# --- Pro-only feature: CSV export -----------------------------------------------------


def test_export_requires_pro(client, org_a):
    response = client.get("/api/projects/export/")

    assert response.status_code == 403
    assert response.data["detail"].code == "plan_upgrade_required"


def test_export_on_pro_returns_only_own_org_rows(client, org_a, org_b, owner):
    set_plan(org_a, "pro")
    set_plan(org_b, "pro")
    ProjectFactory(organization=org_a, name="mine", created_by=owner)
    ProjectFactory(organization=org_b, name="theirs")

    response = client.get("/api/projects/export/")

    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    rows = list(csv.reader(io.StringIO(response.content.decode())))
    assert rows[0] == ["id", "name", "description", "created_by", "created_at"]
    assert [row[1] for row in rows[1:]] == ["mine"]
    assert AuditLogEntry.all_tenants.filter(organization=org_a, action="project.export").exists()


@pytest.mark.parametrize("payload", ["=HYPERLINK(\"http://evil\")", "+1+1", "-2", "@SUM(A1)"])
def test_export_neutralises_spreadsheet_formulas(client, org_a, owner, payload):
    set_plan(org_a, "pro")
    ProjectFactory(organization=org_a, name=payload, created_by=owner)

    rows = list(csv.reader(io.StringIO(client.get("/api/projects/export/").content.decode())))

    assert rows[1][1] == "'" + payload


@pytest.mark.parametrize("role", [ADMIN, MEMBER])
def test_export_is_available_to_every_role_on_pro(basic_client, org_a, make_org_member, role):
    set_plan(org_a, "pro")
    user = make_org_member(org_a, role=role)

    assert basic_client(user, org_slug=org_a.slug).get("/api/projects/export/").status_code == 200
