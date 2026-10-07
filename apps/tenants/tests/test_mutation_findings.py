"""Tests added to kill surviving mutants found by mutmut on apps/tenants.

Each test names the behaviour a surviving mutant broke without any test
noticing (see docs/qa-report.md, "Mutation testing").
"""

import io
import re
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditLogEntry
from apps.billing.models import Subscription
from apps.billing.services import usage
from apps.projects.models import Project
from apps.projects.tests.factories import ProjectFactory
from apps.tenants import exceptions
from apps.tenants.context import tenant_context
from apps.tenants.models import Invitation, Membership
from apps.tenants.tests.factories import MembershipFactory

pytestmark = pytest.mark.django_db

OWNER, ADMIN, MEMBER = Membership.Role.OWNER, Membership.Role.ADMIN, Membership.Role.MEMBER


# --- last-owner guard ------------------------------------------------------------------


def test_owners_of_other_orgs_do_not_count_as_owners_here(org_a, org_b):
    """Mutant: _is_last_owner without the organization filter."""
    MembershipFactory(organization=org_b, role=OWNER)
    only_owner = MembershipFactory(organization=org_a, role=OWNER)

    only_owner.role = ADMIN
    with pytest.raises(exceptions.LastOwnerError):
        only_owner.save()
    only_owner.refresh_from_db()
    with pytest.raises(exceptions.LastOwnerError):
        only_owner.delete()


def test_delete_checks_the_stored_role_not_the_unsaved_one(org_a):
    """D-19: delete() trusted the in-memory role, so an unsaved demotion
    followed by delete() removed the organization's last owner."""
    only_owner = MembershipFactory(organization=org_a, role=OWNER)

    only_owner.role = ADMIN  # changed in memory only
    with pytest.raises(exceptions.LastOwnerError):
        only_owner.delete()

    assert Membership.objects.filter(pk=only_owner.pk, role=OWNER).exists()


def test_resaving_the_last_owner_unchanged_is_allowed(org_a):
    """Mutant: `not adding and role != OWNER` -> `or`."""
    only_owner = MembershipFactory(organization=org_a, role=OWNER)

    only_owner.save()

    assert Membership.objects.get(pk=only_owner.pk).role == OWNER


def test_demotion_locks_the_organization_row(org_a):
    """Mutant: _lock_organization locking pk=None (no row)."""
    MembershipFactory(organization=org_a, role=OWNER)
    second = MembershipFactory(organization=org_a, role=OWNER)
    second.role = ADMIN

    with CaptureQueriesContext(connection) as ctx:
        second.save()

    locks = [q["sql"] for q in ctx.captured_queries if "FOR UPDATE" in q["sql"]]
    assert any("tenants_organization" in sql and str(org_a.pk) in sql for sql in locks), locks


def test_deleting_a_user_who_owns_nothing_is_allowed(org_a):
    MembershipFactory(organization=org_a, role=OWNER)
    admin = MembershipFactory(organization=org_a, role=ADMIN).user

    admin.delete()

    assert not User.objects.filter(pk=admin.pk).exists()


# --- TenantOwnedModel / TenantQuerySet ----------------------------------------------


def test_rows_from_bulk_create_can_be_saved_again(org_a):
    """Mutant: save() treating a missing _loaded_organization_id as None."""
    user = UserFactory()
    with tenant_context(org_a):
        [project] = Project.objects.bulk_create([Project(name="bulk", created_by=user)])
        project.name = "renamed"
        project.save()

    assert Project.all_tenants.get(pk=project.pk).name == "renamed"


def test_bulk_update_of_own_rows_works(org_a):
    projects = ProjectFactory.create_batch(2, organization=org_a)
    with tenant_context(org_a):
        rows = list(Project.objects.all())
        for row in rows:
            row.name = "bulk-updated"
        Project.objects.bulk_update(rows, ["name"])

    assert set(Project.all_tenants.filter(pk__in=[p.pk for p in projects]).values_list("name", flat=True)) == {
        "bulk-updated"
    }


@pytest.mark.parametrize("field", ["organization", "organization_id"])
def test_bulk_update_cannot_change_organization(org_a, org_b, field):
    project = ProjectFactory(organization=org_a)
    with tenant_context(org_a):
        row = Project.objects.get(pk=project.pk)
        with pytest.raises(exceptions.TenantMismatchError):
            Project.objects.bulk_update([row], [field, "name"])

    assert Project.all_tenants.get(pk=project.pk).organization_id == org_a.id


def test_bulk_update_refuses_rows_of_another_org(org_a, org_b):
    theirs = Project.all_tenants.get(pk=ProjectFactory(organization=org_b, name="theirs").pk)
    theirs.name = "tampered"

    with tenant_context(org_a), pytest.raises(exceptions.TenantMismatchError):
        Project.objects.bulk_update([theirs], ["name"])

    assert Project.all_tenants.get(pk=theirs.pk).name == "theirs"


def test_bulk_update_requires_a_tenant(org_a):
    row = Project.all_tenants.get(pk=ProjectFactory(organization=org_a).pk)

    with pytest.raises(exceptions.NoActiveTenantError):
        Project.objects.bulk_update([row], ["name"])


def test_mismatch_errors_name_both_organizations(org_a, org_b):
    with tenant_context(org_a), pytest.raises(exceptions.TenantMismatchError) as info:
        Project.objects.create(name="x", organization=org_b, created_by=UserFactory())

    assert str(org_b.id) in str(info.value) and str(org_a.id) in str(info.value)


# --- invitations --------------------------------------------------------------------


@pytest.fixture
def owner_a(org_a):
    return MembershipFactory(organization=org_a, role=OWNER).user


@pytest.fixture
def invite(basic_client, django_capture_on_commit_callbacks, mailoutbox):
    def _invite(inviter, org, email, role=MEMBER):
        with django_capture_on_commit_callbacks(execute=True):
            response = basic_client(inviter, org_slug=org.slug).post(
                "/api/invitations/", {"email": email, "role": role}, format="json"
            )
        token = re.search(r"token=([\w-]+)", mailoutbox[-1].body).group(1) if response.status_code == 201 else None
        return response, token

    return _invite


def test_invitation_token_has_256_bits(invite, org_a, owner_a):
    _, token = invite(owner_a, org_a, "bits@example.com")

    assert len(token) == 43  # token_urlsafe(32): 32 random bytes, base64url


def test_invitation_email_subject_sender_and_link(invite, org_a, owner_a, mailoutbox, settings):
    invite(owner_a, org_a, "mail@example.com", role=ADMIN)

    message = mailoutbox[-1]
    assert message.subject == "You're invited to join Org A"
    assert message.from_email == settings.DEFAULT_FROM_EMAIL
    assert owner_a.email in message.body and "as admin" in message.body


def test_invitation_create_and_accept_audit_entries_are_complete(invite, api_client, org_a, owner_a):
    _, token = invite(owner_a, org_a, "audit@example.com", role=ADMIN)
    api_client.post("/api/invitations/accept/", {"token": token, "password": "Audit-Accept-55"}, format="json")

    invitation = Invitation.all_tenants.get()
    created = AuditLogEntry.all_tenants.get(action="invitation.create")
    accepted = AuditLogEntry.all_tenants.get(action="invitation.accept")
    assert (created.actor, created.target_id) == (owner_a, str(invitation.id))
    assert created.changes == {"email": "audit@example.com", "role": "admin"}
    assert (accepted.actor.email, accepted.target_id) == ("audit@example.com", str(invitation.id))
    assert accepted.changes == {"email": "audit@example.com", "role": "admin"}


def test_revoke_audit_entry_is_complete(basic_client, invite, org_a, owner_a):
    invite(owner_a, org_a, "rev@example.com")
    invitation = Invitation.all_tenants.get()

    basic_client(owner_a, org_slug=org_a.slug).delete(f"/api/invitations/{invitation.id}/")

    entry = AuditLogEntry.all_tenants.get(action="invitation.revoke")
    assert (entry.actor, entry.target_id, entry.changes) == (owner_a, str(invitation.id), {"email": "rev@example.com"})


def test_accept_saves_the_invitees_names(invite, api_client, org_a, owner_a):
    _, token = invite(owner_a, org_a, "named@example.com")

    api_client.post(
        "/api/invitations/accept/",
        {"token": token, "password": "Named-Person-42", "first_name": "Ada", "last_name": "Lovelace"},
        format="json",
    )

    user = User.objects.get(email="named@example.com")
    assert (user.first_name, user.last_name) == ("Ada", "Lovelace")


@pytest.mark.parametrize(
    "password, extra",
    [
        ("similarinvitee", {}),  # similar to the email "similarinvitee@..."
        ("Bartholomew1", {"first_name": "Bartholomew"}),
        ("Vanderbilt22", {"last_name": "Vanderbilt"}),
    ],
)
def test_accept_rejects_passwords_similar_to_the_invitee(invite, api_client, org_a, owner_a, password, extra):
    _, token = invite(owner_a, org_a, "similarinvitee@example.com")

    response = api_client.post(
        "/api/invitations/accept/", {"token": token, "password": password, **extra}, format="json"
    )

    assert response.status_code == 400
    assert "password" in response.data


def test_accept_error_keys_are_stable(invite, api_client, basic_client, org_a, owner_a):
    _, token = invite(owner_a, org_a, "keys@example.com")

    no_password = api_client.post("/api/invitations/accept/", {"token": token}, format="json")
    bad_token = api_client.post("/api/invitations/accept/", {"token": "nope", "password": "x"}, format="json")
    user = UserFactory(email="keys2@example.com")
    _, token2 = invite(owner_a, org_a, user.email)
    MembershipFactory(user=user, organization=org_a)
    already = basic_client(user).post("/api/invitations/accept/", {"token": token2}, format="json")

    assert list(no_password.data) == ["password"]
    assert list(bad_token.data) == ["token"]
    assert list(already.data) == ["token"]


def test_reinvite_only_closes_that_emails_expired_invitation(invite, org_a, owner_a, api_client):
    """Mutants: the expiry clean-up filter losing its email/accepted conditions."""
    Subscription.objects.update_or_create(organization=org_a, defaults={"plan": "pro"})
    _, accepted_token = invite(owner_a, org_a, "accepted@example.com")
    api_client.post(
        "/api/invitations/accept/", {"token": accepted_token, "password": "Accepted-Pass-90"}, format="json"
    )
    invite(owner_a, org_a, "other@example.com")
    invite(owner_a, org_a, "again@example.com")
    Invitation.all_tenants.update(expires_at=timezone.now() - timedelta(seconds=1))

    response, _ = invite(owner_a, org_a, "again@example.com")

    assert response.status_code == 201
    statuses = [(i.email, i.status) for i in Invitation.all_tenants.order_by("id")]
    assert statuses == [
        ("accepted@example.com", "accepted"),
        ("other@example.com", "expired"),
        ("again@example.com", "revoked"),
        ("again@example.com", "pending"),
    ]
    assert Invitation.all_tenants.filter(email="again@example.com", revoked_at__isnull=False).count() == 1


def test_accepted_and_revoked_invitations_do_not_reserve_seats(invite, basic_client, api_client, org_a, owner_a):
    """Mutants: pending() losing its accepted_at / revoked_at conditions."""
    _, token = invite(owner_a, org_a, "joined@example.com")
    api_client.post("/api/invitations/accept/", {"token": token, "password": "Joined-Pass-77"}, format="json")
    invite(owner_a, org_a, "revoked@example.com")
    revoked = Invitation.all_tenants.get(email="revoked@example.com")
    basic_client(owner_a, org_slug=org_a.slug).delete(f"/api/invitations/{revoked.id}/")

    assert usage(org_a)["pending_invitations"] == 0
    # 2 members, nothing pending: the 3rd seat is still free.
    response, _ = invite(owner_a, org_a, "third@example.com")
    assert response.status_code == 201


def test_revoked_email_can_be_invited_again(invite, basic_client, org_a, owner_a):
    invite(owner_a, org_a, "back@example.com")
    first = Invitation.all_tenants.get()
    basic_client(owner_a, org_slug=org_a.slug).delete(f"/api/invitations/{first.id}/")

    response, _ = invite(owner_a, org_a, "back@example.com")

    assert response.status_code == 201


def test_revoking_an_accepted_invitation_reports_detail(invite, basic_client, api_client, org_a, owner_a):
    _, token = invite(owner_a, org_a, "acc@example.com")
    api_client.post("/api/invitations/accept/", {"token": token, "password": "Accepted-Pass-12"}, format="json")
    invitation = Invitation.all_tenants.get()

    response = basic_client(owner_a, org_slug=org_a.slug).delete(f"/api/invitations/{invitation.id}/")

    assert response.status_code == 400
    assert "detail" in response.data


# --- members API audit details ------------------------------------------------------------


def test_member_audit_entries_are_complete(basic_client, org_a, owner_a):
    target = MembershipFactory(organization=org_a, role=MEMBER)
    client = basic_client(owner_a, org_slug=org_a.slug)

    client.patch(f"/api/members/{target.id}/", {"role": ADMIN}, format="json")
    client.delete(f"/api/members/{target.id}/")

    change = AuditLogEntry.all_tenants.get(action="member.role_change")
    removal = AuditLogEntry.all_tenants.get(action="member.remove")
    assert change.target_id == str(target.id)
    assert (removal.actor, removal.target_id) == (owner_a, str(target.id))
    assert removal.changes == {"user": target.user.email, "role": "admin"}


# --- tenant resolution and schema --------------------------------------------------------


def test_missing_header_error_names_the_header(basic_client, org_a, owner_a):
    response = basic_client(owner_a).get("/api/projects/")

    assert response.status_code == 400
    assert "X-Org" in response.data["detail"]


def test_schema_generates_without_warnings():
    """Mutants: tenant_queryset not detecting schema generation (managers raise)."""
    call_command("spectacular", "--validate", "--fail-on-warn", stdout=io.StringIO())


# --- dumpdata ----------------------------------------------------------------------------


def test_dumpdata_unknown_org_is_a_clear_error():
    from django.core.management import CommandError

    with pytest.raises(CommandError, match="no-such-org"):
        call_command("dumpdata", "projects", org="no-such-org", stdout=io.StringIO())
