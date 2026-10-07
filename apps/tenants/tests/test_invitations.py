import re
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditLogEntry
from apps.billing.models import Subscription
from apps.tenants.models import Invitation, Membership
from apps.tenants.tests.factories import MembershipFactory

pytestmark = pytest.mark.django_db

OWNER, ADMIN, MEMBER = Membership.Role.OWNER, Membership.Role.ADMIN, Membership.Role.MEMBER
NEW_PASSWORD = "Fresh-Invitee-77"


@pytest.fixture
def invite(basic_client, django_capture_on_commit_callbacks, mailoutbox):
    """POST an invitation as `inviter`; return (response, raw_token or None)."""

    def _invite(inviter, org, email, role=MEMBER):
        client = basic_client(inviter, org_slug=org.slug)
        with django_capture_on_commit_callbacks(execute=True):
            response = client.post("/api/invitations/", {"email": email, "role": role}, format="json")
        token = None
        if response.status_code == 201:
            match = re.search(r"token=([\w-]+)", mailoutbox[-1].body)
            token = match.group(1)
        return response, token

    return _invite


@pytest.fixture
def owner_a(org_a, make_org_member):
    return make_org_member(org_a, role=OWNER)


def accept(client, token, **extra):
    return client.post("/api/invitations/accept/", {"token": token, **extra}, format="json")


# --- creating -----------------------------------------------------------------


def test_admin_invites_and_email_carries_the_only_copy_of_the_token(
    invite, org_a, make_org_member, mailoutbox
):
    admin = make_org_member(org_a, role=ADMIN)

    response, token = invite(admin, org_a, "New.Person@Example.com")

    assert response.status_code == 201
    assert response.data["email"] == "new.person@example.com"
    assert response.data["status"] == "pending"
    assert token not in str(response.data)
    assert mailoutbox[-1].to == ["new.person@example.com"]
    invitation = Invitation.all_tenants.get()
    assert invitation.token_hash == Invitation.hash_token(token) != token
    assert AuditLogEntry.all_tenants.filter(organization=org_a, action="invitation.create").exists()


def test_member_cannot_invite(invite, org_a, make_org_member):
    member = make_org_member(org_a, role=MEMBER)

    response, _ = invite(member, org_a, "x@example.com")

    assert response.status_code == 403
    assert not Invitation.all_tenants.exists()


def test_admin_cannot_invite_an_owner_but_owner_can(invite, org_a, owner_a, make_org_member):
    admin = make_org_member(org_a, role=ADMIN)

    by_admin, _ = invite(admin, org_a, "boss@example.com", role=OWNER)
    by_owner, _ = invite(owner_a, org_a, "boss@example.com", role=OWNER)

    assert by_admin.status_code == 403
    assert by_owner.status_code == 201


def test_duplicate_pending_invitation_is_rejected(invite, org_a, owner_a):
    invite(owner_a, org_a, "dup@example.com")

    response, _ = invite(owner_a, org_a, "DUP@example.com")

    assert response.status_code == 400
    assert Invitation.all_tenants.count() == 1


def test_existing_member_cannot_be_invited(invite, org_a, owner_a, make_org_member):
    member = make_org_member(org_a)

    response, _ = invite(owner_a, org_a, member.email.upper())

    assert response.status_code == 400


def test_expired_invitation_can_be_replaced(invite, org_a, owner_a):
    invite(owner_a, org_a, "late@example.com")
    Invitation.all_tenants.update(expires_at=timezone.now() - timedelta(seconds=1))

    response, _ = invite(owner_a, org_a, "late@example.com")

    assert response.status_code == 201
    statuses = sorted(i.status for i in Invitation.all_tenants.all())
    assert statuses == ["pending", "revoked"]


# --- accepting ----------------------------------------------------------------


def test_new_user_accepts_with_password(invite, api_client, basic_client, org_a, owner_a):
    _, token = invite(owner_a, org_a, "newbie@example.com", role=ADMIN)

    response = accept(api_client, token, password=NEW_PASSWORD, first_name="New")

    assert response.status_code == 200
    assert response.data == {"organization": {"slug": "org-a", "name": "Org A"}, "role": "admin"}
    user = User.objects.get(email="newbie@example.com")
    assert Membership.objects.get(user=user, organization=org_a).role == ADMIN
    invitation = Invitation.all_tenants.get()
    assert invitation.status == "accepted" and invitation.accepted_by == user
    assert basic_client(user, org_slug="org-a", password=NEW_PASSWORD).get("/api/projects/").status_code == 200
    assert AuditLogEntry.all_tenants.filter(organization=org_a, action="invitation.accept").exists()


def test_new_user_must_supply_a_valid_password(invite, api_client, org_a, owner_a):
    _, token = invite(owner_a, org_a, "newbie@example.com")

    missing = accept(api_client, token)
    weak = accept(api_client, token, password="123")

    assert (missing.status_code, weak.status_code) == (400, 400)
    assert not User.objects.filter(email="newbie@example.com").exists()
    assert Invitation.all_tenants.get().status == "pending"


def test_existing_user_accepts_by_authenticating(invite, basic_client, org_a, org_b, owner_a, make_org_member):
    existing = make_org_member(org_b)
    _, token = invite(owner_a, org_a, existing.email)

    response = accept(basic_client(existing), token)

    assert response.status_code == 200
    assert Membership.objects.filter(user=existing, organization=org_a).exists()


def test_existing_user_cannot_accept_anonymously(invite, api_client, org_a, org_b, owner_a, make_org_member):
    existing = make_org_member(org_b)
    _, token = invite(owner_a, org_a, existing.email)

    response = accept(api_client, token, password=NEW_PASSWORD)

    assert response.status_code == 401
    assert not Membership.objects.filter(user=existing, organization=org_a).exists()
    assert existing.check_password(NEW_PASSWORD) is False


def test_token_cannot_be_used_by_a_different_account(invite, basic_client, org_a, owner_a):
    _, token = invite(owner_a, org_a, "intended@example.com")
    thief = UserFactory()

    response = accept(basic_client(thief), token)

    assert response.status_code == 403
    assert not Membership.objects.filter(user=thief, organization=org_a).exists()
    assert Invitation.all_tenants.get().status == "pending"


def test_email_match_is_case_insensitive(invite, basic_client, org_a, owner_a):
    user = UserFactory(email="Mixed.Case@example.com")
    _, token = invite(owner_a, org_a, "mixed.case@EXAMPLE.com")

    assert accept(basic_client(user), token).status_code == 200


def test_token_is_single_use(invite, api_client, org_a, owner_a):
    _, token = invite(owner_a, org_a, "once@example.com")
    first = accept(api_client, token, password=NEW_PASSWORD)

    second = accept(api_client, token, password=NEW_PASSWORD)

    assert (first.status_code, second.status_code) == (200, 400)
    assert Membership.objects.filter(organization=org_a, user__email="once@example.com").count() == 1


def test_expired_token_is_rejected(invite, api_client, org_a, owner_a):
    _, token = invite(owner_a, org_a, "late@example.com")
    Invitation.all_tenants.update(expires_at=timezone.now() - timedelta(seconds=1))

    response = accept(api_client, token, password=NEW_PASSWORD)

    assert response.status_code == 400
    assert not User.objects.filter(email="late@example.com").exists()


def test_token_one_second_before_expiry_still_works(invite, api_client, org_a, owner_a):
    _, token = invite(owner_a, org_a, "just@example.com")
    Invitation.all_tenants.update(expires_at=timezone.now() + timedelta(seconds=5))

    assert accept(api_client, token, password=NEW_PASSWORD).status_code == 200


@pytest.mark.parametrize("token", ["", "not-a-real-token", "x" * 500])
def test_unknown_tokens_are_rejected(api_client, token):
    assert accept(api_client, token, password=NEW_PASSWORD).status_code == 400


def test_invitation_ttl_is_seven_days(invite, org_a, owner_a):
    before = timezone.now()
    invite(owner_a, org_a, "ttl@example.com")

    expires = Invitation.all_tenants.get().expires_at
    assert timedelta(days=7) - timedelta(seconds=5) < expires - before <= timedelta(days=7) + timedelta(seconds=5)


def test_accepting_joins_only_the_inviting_org(invite, basic_client, org_a, org_b, owner_a, make_org_member):
    user = make_org_member(org_b)
    _, token = invite(owner_a, org_a, user.email)
    client = basic_client(user, org_slug=org_b.slug)  # X-Org of another org is ignored

    accept(client, token)

    assert set(user.memberships.values_list("organization__slug", flat=True)) == {"org-a", "org-b"}
    assert user.memberships.get(organization=org_b).role == MEMBER


def test_already_member_cannot_accept_twice(invite, basic_client, org_a, owner_a):
    user = UserFactory()
    _, token = invite(owner_a, org_a, user.email)
    MembershipFactory(user=user, organization=org_a)  # joined by another path meanwhile

    response = accept(basic_client(user), token)

    assert response.status_code == 400
    assert Membership.objects.filter(user=user, organization=org_a).count() == 1


# --- revoking and listing ----------------------------------------------------------


def test_revoked_token_cannot_be_used(invite, basic_client, api_client, org_a, owner_a):
    _, token = invite(owner_a, org_a, "gone@example.com")
    invitation = Invitation.all_tenants.get()

    revoke = basic_client(owner_a, org_slug=org_a.slug).delete(f"/api/invitations/{invitation.id}/")

    assert revoke.status_code == 204
    assert Invitation.all_tenants.get().status == "revoked"
    assert accept(api_client, token, password=NEW_PASSWORD).status_code == 400
    assert AuditLogEntry.all_tenants.filter(organization=org_a, action="invitation.revoke").exists()


def test_accepted_invitation_cannot_be_revoked(invite, basic_client, api_client, org_a, owner_a):
    _, token = invite(owner_a, org_a, "done@example.com")
    accept(api_client, token, password=NEW_PASSWORD)
    invitation = Invitation.all_tenants.get()

    response = basic_client(owner_a, org_slug=org_a.slug).delete(f"/api/invitations/{invitation.id}/")

    assert response.status_code == 400
    assert Invitation.all_tenants.get().status == "accepted"


def test_list_shows_only_own_org_invitations(invite, basic_client, org_a, org_b, owner_a, make_org_member):
    owner_b = make_org_member(org_b, role=OWNER)
    invite(owner_a, org_a, "for-a@example.com")
    invite(owner_b, org_b, "for-b@example.com")

    rows = basic_client(owner_a, org_slug=org_a.slug).get("/api/invitations/").data["results"]

    assert [row["email"] for row in rows] == ["for-a@example.com"]


def test_cannot_revoke_another_orgs_invitation(invite, basic_client, org_a, org_b, owner_a, make_org_member):
    owner_b = make_org_member(org_b, role=OWNER)
    invite(owner_b, org_b, "for-b@example.com")
    theirs = Invitation.all_tenants.get()

    response = basic_client(owner_a, org_slug=org_a.slug).delete(f"/api/invitations/{theirs.id}/")

    assert response.status_code == 404
    assert Invitation.all_tenants.get().status == "pending"


# --- plan limits (Free: 3 members) ---------------------------------------------------


def test_free_plan_counts_pending_invitations_as_seats(invite, org_a, owner_a, make_org_member):
    make_org_member(org_a)  # 2 members
    first, _ = invite(owner_a, org_a, "third@example.com")  # 3rd seat reserved

    fourth, _ = invite(owner_a, org_a, "fourth@example.com")

    assert first.status_code == 201
    assert fourth.status_code == 403
    assert fourth.data["detail"].code == "plan_limit_reached"


def test_free_plan_blocks_acceptance_when_full(invite, api_client, org_a, owner_a, make_org_member):
    make_org_member(org_a)
    _, token = invite(owner_a, org_a, "third@example.com")
    make_org_member(org_a)  # org filled to 3 by another path (e.g. admin)

    response = accept(api_client, token, password=NEW_PASSWORD)

    assert response.status_code == 403
    assert not User.objects.filter(email="third@example.com").exists()
    assert Invitation.all_tenants.get().status == "pending"


def test_pro_plan_has_no_member_limit(invite, org_a, owner_a, make_org_member):
    Subscription.objects.update_or_create(organization=org_a, defaults={"plan": "pro"})
    for _ in range(4):
        make_org_member(org_a)

    response, _ = invite(owner_a, org_a, "sixth@example.com")

    assert response.status_code == 201
