import pytest

from apps.audit.models import AuditLogEntry
from apps.tenants.models import Membership

pytestmark = pytest.mark.django_db

OWNER, ADMIN, MEMBER = Membership.Role.OWNER, Membership.Role.ADMIN, Membership.Role.MEMBER


def membership(user, org):
    return Membership.objects.get(user=user, organization=org)


@pytest.fixture
def team(org_a, make_org_member):
    return {
        "owner": make_org_member(org_a, role=OWNER),
        "admin": make_org_member(org_a, role=ADMIN),
        "member": make_org_member(org_a, role=MEMBER),
        "member2": make_org_member(org_a, role=MEMBER),
    }


@pytest.mark.parametrize("role", ["owner", "admin", "member"])
def test_every_role_can_list_members_of_own_org_only(basic_client, org_a, org_b, team, make_org_member, role):
    make_org_member(org_b, role=OWNER)

    response = basic_client(team[role], org_slug=org_a.slug).get("/api/members/")

    assert response.status_code == 200
    emails = {row["user"]["email"] for row in response.data["results"]}
    assert emails == {u.email for u in team.values()}


def test_owner_changes_a_role_and_it_is_audited(basic_client, org_a, team):
    target = membership(team["member"], org_a)

    response = basic_client(team["owner"], org_slug=org_a.slug).patch(
        f"/api/members/{target.id}/", {"role": ADMIN}, format="json"
    )

    assert response.status_code == 200
    assert membership(team["member"], org_a).role == ADMIN
    entry = AuditLogEntry.all_tenants.get(organization=org_a, action="member.role_change")
    assert entry.changes == {"user": team["member"].email, "role": ["member", "admin"]}
    assert entry.actor == team["owner"]


@pytest.mark.parametrize("actor", ["admin", "member"])
def test_non_owners_cannot_change_roles(basic_client, org_a, team, actor):
    target = membership(team["member2"], org_a)

    response = basic_client(team[actor], org_slug=org_a.slug).patch(
        f"/api/members/{target.id}/", {"role": OWNER}, format="json"
    )

    assert response.status_code == 403
    assert membership(team["member2"], org_a).role == MEMBER


def test_admin_cannot_promote_themselves(basic_client, org_a, team):
    own = membership(team["admin"], org_a)

    response = basic_client(team["admin"], org_slug=org_a.slug).patch(
        f"/api/members/{own.id}/", {"role": OWNER}, format="json"
    )

    assert response.status_code == 403
    assert membership(team["admin"], org_a).role == ADMIN


def test_last_owner_cannot_be_demoted(basic_client, org_a, team):
    own = membership(team["owner"], org_a)

    response = basic_client(team["owner"], org_slug=org_a.slug).patch(
        f"/api/members/{own.id}/", {"role": ADMIN}, format="json"
    )

    assert response.status_code == 409
    assert response.data["detail"].code == "last_owner"
    assert membership(team["owner"], org_a).role == OWNER
    assert not AuditLogEntry.all_tenants.filter(action="member.role_change").exists()


def test_owner_can_hand_over_ownership_then_step_down(basic_client, org_a, team):
    client = basic_client(team["owner"], org_slug=org_a.slug)
    successor = membership(team["admin"], org_a)
    own = membership(team["owner"], org_a)

    promote = client.patch(f"/api/members/{successor.id}/", {"role": OWNER}, format="json")
    step_down = client.patch(f"/api/members/{own.id}/", {"role": ADMIN}, format="json")

    assert (promote.status_code, step_down.status_code) == (200, 200)
    assert membership(team["admin"], org_a).role == OWNER


def test_invalid_role_is_rejected(basic_client, org_a, team):
    target = membership(team["member"], org_a)

    response = basic_client(team["owner"], org_slug=org_a.slug).patch(
        f"/api/members/{target.id}/", {"role": "superuser"}, format="json"
    )

    assert response.status_code == 400


def test_user_and_org_cannot_be_reassigned_via_patch(basic_client, org_a, org_b, team):
    target = membership(team["member"], org_a)

    basic_client(team["owner"], org_slug=org_a.slug).patch(
        f"/api/members/{target.id}/",
        {"user": team["owner"].id, "organization": org_b.id, "role": MEMBER},
        format="json",
    )

    target.refresh_from_db()
    assert (target.user_id, target.organization_id) == (team["member"].id, org_a.id)


def test_put_is_not_allowed(basic_client, org_a, team):
    target = membership(team["member"], org_a)

    response = basic_client(team["owner"], org_slug=org_a.slug).put(
        f"/api/members/{target.id}/", {"role": ADMIN}, format="json"
    )

    assert response.status_code == 405


@pytest.mark.parametrize(
    "actor, victim, status",
    [
        ("owner", "admin", 204),
        ("owner", "member", 204),
        ("admin", "member", 204),
        ("admin", "owner", 403),
        ("member", "member2", 403),
        ("member", "admin", 403),
    ],
)
def test_removal_matrix(basic_client, org_a, team, actor, victim, status):
    target = membership(team[victim], org_a)

    response = basic_client(team[actor], org_slug=org_a.slug).delete(f"/api/members/{target.id}/")

    assert response.status_code == status
    assert Membership.objects.filter(pk=target.pk).exists() == (status != 204)


def test_admin_cannot_remove_another_admin(basic_client, org_a, team, make_org_member):
    other_admin = make_org_member(org_a, role=ADMIN)
    target = membership(other_admin, org_a)

    response = basic_client(team["admin"], org_slug=org_a.slug).delete(f"/api/members/{target.id}/")

    assert response.status_code == 403


@pytest.mark.parametrize("role", ["admin", "member"])
def test_anyone_can_leave(basic_client, org_a, team, role):
    own = membership(team[role], org_a)

    response = basic_client(team[role], org_slug=org_a.slug).delete(f"/api/members/{own.id}/")

    assert response.status_code == 204
    entry = AuditLogEntry.all_tenants.get(organization=org_a, action="member.leave")
    assert entry.target_id == str(own.id)


def test_last_owner_cannot_leave(basic_client, org_a, team):
    own = membership(team["owner"], org_a)

    response = basic_client(team["owner"], org_slug=org_a.slug).delete(f"/api/members/{own.id}/")

    assert response.status_code == 409
    assert Membership.objects.filter(pk=own.pk).exists()
    assert not AuditLogEntry.all_tenants.filter(action__startswith="member.").exists()


def test_removal_is_audited_with_target(basic_client, org_a, team):
    target = membership(team["member"], org_a)

    basic_client(team["owner"], org_slug=org_a.slug).delete(f"/api/members/{target.id}/")

    entry = AuditLogEntry.all_tenants.get(organization=org_a, action="member.remove")
    assert (entry.target_id, entry.changes["user"]) == (str(target.id), team["member"].email)


def test_removed_member_loses_access_immediately(basic_client, org_a, team):
    target = membership(team["member"], org_a)
    basic_client(team["owner"], org_slug=org_a.slug).delete(f"/api/members/{target.id}/")

    response = basic_client(team["member"], org_slug=org_a.slug).get("/api/projects/")

    assert response.status_code == 403


def test_cannot_touch_members_of_another_org(basic_client, org_a, org_b, team, make_org_member):
    outsider = make_org_member(org_b, role=MEMBER)
    target = membership(outsider, org_b)
    client = basic_client(team["owner"], org_slug=org_a.slug)

    get = client.get(f"/api/members/{target.id}/")
    patch = client.patch(f"/api/members/{target.id}/", {"role": ADMIN}, format="json")
    delete = client.delete(f"/api/members/{target.id}/")

    assert (get.status_code, patch.status_code, delete.status_code) == (404, 404, 404)
    assert membership(outsider, org_b).role == MEMBER
