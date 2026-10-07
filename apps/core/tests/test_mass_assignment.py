"""Mass assignment: every write endpoint ignores fields the client must not set."""

import re

import pytest

from apps.accounts.models import User
from apps.billing.models import Subscription
from apps.projects.models import Project
from apps.projects.tests.factories import ProjectFactory
from apps.tenants.models import Invitation, Membership

pytestmark = pytest.mark.django_db

OWNER = Membership.Role.OWNER


@pytest.fixture
def setup(basic_client, org_a, org_b, make_org_member):
    owner = make_org_member(org_a, role=OWNER)
    other = make_org_member(org_b, role=OWNER)
    return {"client": basic_client(owner, org_slug=org_a.slug), "owner": owner, "other": other}


def test_project_create(setup, org_a, org_b):
    response = setup["client"].post(
        "/api/projects/",
        {
            "name": "x",
            "id": 999999,
            "organization": org_b.slug,
            "organization_id": org_b.id,
            "created_by": setup["other"].id,
            "created_at": "2000-01-01T00:00:00Z",
        },
        format="json",
    )

    project = Project.all_tenants.get(pk=response.data["id"])
    assert project.pk != 999999
    assert (project.organization_id, project.created_by_id) == (org_a.id, setup["owner"].id)
    assert project.created_at.year > 2000


@pytest.mark.parametrize("method", ["patch", "put"])
def test_project_update(setup, org_a, org_b, method):
    project = ProjectFactory(organization=org_a, created_by=setup["owner"])

    getattr(setup["client"], method)(
        f"/api/projects/{project.id}/",
        {"name": "y", "id": 1, "organization_id": org_b.id, "created_by": setup["other"].id},
        format="json",
    )

    project.refresh_from_db()
    assert (project.organization_id, project.created_by_id) == (org_a.id, setup["owner"].id)


def test_member_patch(setup, org_a, org_b, make_org_member):
    target = Membership.objects.get(user=make_org_member(org_a), organization=org_a)

    setup["client"].patch(
        f"/api/members/{target.id}/",
        {"role": "member", "user": setup["owner"].id, "organization": org_b.id, "id": 1},
        format="json",
    )

    target.refresh_from_db()
    assert (target.user_id, target.organization_id) == (target.user_id, org_a.id)
    assert Membership.objects.filter(organization=org_b).count() == 1


def test_invitation_create(setup, org_a, org_b):
    response = setup["client"].post(
        "/api/invitations/",
        {
            "email": "m@example.com",
            "organization": org_b.id,
            "token_hash": "0" * 64,
            "invited_by": setup["other"].id,
            "accepted_at": "2030-01-01T00:00:00Z",
            "expires_at": "2099-01-01T00:00:00Z",
            "revoked_at": None,
            "status": "accepted",
        },
        format="json",
    )

    invitation = Invitation.all_tenants.get(pk=response.data["id"])
    assert invitation.organization_id == org_a.id
    assert invitation.token_hash != "0" * 64
    assert invitation.invited_by_id == setup["owner"].id
    assert invitation.status == "pending"
    assert invitation.expires_at.year < 2099


def test_subscription_patch(setup, org_a, org_b):
    setup["client"].patch(
        "/api/subscription/",
        {"plan": "free", "organization": org_b.id, "limits": {"max_projects": 10**6}},
        format="json",
    )

    assert Subscription.objects.get(organization=org_a).limits.max_projects == 5
    assert not Subscription.objects.filter(organization=org_b).exists()


def test_signup(api_client):
    api_client.post(
        "/api/auth/signup/",
        {
            "email": "ma@example.com",
            "password": "Mass-Assign-Pass-3",
            "organization_name": "MA",
            "is_staff": True,
            "is_superuser": True,
            "is_active": False,
            "role": "member",
            "plan": "pro",
        },
        format="json",
    )

    user = User.objects.get(email="ma@example.com")
    assert (user.is_staff, user.is_superuser, user.is_active) == (False, False, True)
    membership = user.memberships.get()
    assert membership.role == OWNER
    assert Subscription.objects.get(organization=membership.organization).plan == "free"


def test_invitation_accept(
    setup, api_client, org_a, org_b, django_capture_on_commit_callbacks, mailoutbox
):
    with django_capture_on_commit_callbacks(execute=True):
        setup["client"].post("/api/invitations/", {"email": "acc@example.com"}, format="json")
    token = re.search(r"token=([\w-]+)", mailoutbox[-1].body).group(1)

    api_client.post(
        "/api/invitations/accept/",
        {"token": token, "password": "Accept-Mass-Pass-8", "role": "owner", "organization": org_b.id},
        format="json",
    )

    user = User.objects.get(email="acc@example.com")
    assert [(m.organization_id, m.role) for m in user.memberships.all()] == [(org_a.id, "member")]
