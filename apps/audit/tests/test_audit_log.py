import pytest

from apps.audit.exceptions import AppendOnlyError
from apps.audit.models import AuditLogEntry
from apps.audit.services import record
from apps.projects.tests.factories import ProjectFactory
from apps.tenants.context import tenant_context
from apps.tenants.models import Membership

pytestmark = pytest.mark.django_db

OWNER, ADMIN, MEMBER = Membership.Role.OWNER, Membership.Role.ADMIN, Membership.Role.MEMBER


def _entries(org, action=None):
    qs = AuditLogEntry.all_tenants.filter(organization=org)
    return qs.filter(action=action) if action else qs


def test_project_create_update_delete_are_recorded(basic_client, org_a, make_org_member):
    owner = make_org_member(org_a, role=OWNER)
    client = basic_client(owner, org_slug=org_a.slug)

    created = client.post("/api/projects/", {"name": "Alpha"}, format="json")
    pid = created.data["id"]
    client.patch(f"/api/projects/{pid}/", {"name": "Beta"}, format="json")
    client.delete(f"/api/projects/{pid}/")

    create = _entries(org_a, "project.create").get()
    update = _entries(org_a, "project.update").get()
    delete = _entries(org_a, "project.delete").get()
    assert (create.actor, create.actor_email, create.target_id) == (owner, owner.email, str(pid))
    assert update.changes == {"name": ["Alpha", "Beta"]}
    assert delete.changes == {"name": "Beta"}
    assert delete.target_type == "projects.project"


def test_update_without_changes_is_not_recorded(basic_client, org_a, make_org_member):
    owner = make_org_member(org_a, role=OWNER)
    project = ProjectFactory(organization=org_a, name="Same")

    basic_client(owner, org_slug=org_a.slug).patch(
        f"/api/projects/{project.id}/", {"name": "Same"}, format="json"
    )

    assert not _entries(org_a, "project.update").exists()


def test_failed_write_leaves_no_audit_entry(basic_client, org_a, make_org_member):
    member = make_org_member(org_a, role=MEMBER)

    basic_client(member, org_slug=org_a.slug).post("/api/projects/", {"name": "x"}, format="json")

    assert not _entries(org_a).exists()


def test_entries_are_assigned_to_the_active_tenant(org_a, org_b):
    with tenant_context(org_b):
        entry = record("custom.event")

    assert entry.organization_id == org_b.id


@pytest.fixture
def entry(org_a):
    with tenant_context(org_a):
        return record("custom.event", changes={"k": "v"})


def test_entry_cannot_be_updated_via_instance(entry):
    entry.action = "tampered"
    with pytest.raises(AppendOnlyError):
        entry.save()


def test_entry_cannot_be_deleted_via_instance(entry):
    with pytest.raises(AppendOnlyError):
        entry.delete()


def test_entries_cannot_be_updated_or_deleted_via_querysets(entry, org_a):
    with pytest.raises(AppendOnlyError):
        AuditLogEntry.all_tenants.filter(pk=entry.pk).update(action="tampered")
    with pytest.raises(AppendOnlyError):
        AuditLogEntry.all_tenants.filter(pk=entry.pk).delete()
    with tenant_context(org_a):
        with pytest.raises(AppendOnlyError):
            AuditLogEntry.objects.update(action="tampered")
        with pytest.raises(AppendOnlyError):
            AuditLogEntry.objects.all().delete()

    assert AuditLogEntry.all_tenants.get(pk=entry.pk).action == "custom.event"


def test_deleting_the_organization_removes_its_log(entry, org_a):
    org_a.delete()

    assert not AuditLogEntry.all_tenants.filter(pk=entry.pk).exists()


def test_actor_email_survives_user_deletion(basic_client, org_a, make_org_member):
    make_org_member(org_a, role=OWNER)
    admin = make_org_member(org_a, role=ADMIN)
    basic_client(admin, org_slug=org_a.slug).post("/api/projects/", {"name": "x"}, format="json")

    admin.delete()

    entry = _entries(org_a, "project.create").get()
    assert entry.actor is None
    assert entry.actor_email == admin.email


@pytest.mark.parametrize("role, status", [(OWNER, 200), (ADMIN, 200), (MEMBER, 403)])
def test_audit_log_api_roles(basic_client, org_a, make_org_member, role, status):
    user = make_org_member(org_a, role=role)

    assert basic_client(user, org_slug=org_a.slug).get("/api/audit-log/").status_code == status


def test_audit_log_api_shows_only_own_org_and_filters(basic_client, org_a, org_b, make_org_member):
    owner = make_org_member(org_a, role=OWNER)
    with tenant_context(org_a):
        record("a.one")
        record("a.two")
    with tenant_context(org_b):
        record("b.secret")

    client = basic_client(owner, org_slug=org_a.slug)
    all_actions = {row["action"] for row in client.get("/api/audit-log/").data["results"]}
    filtered = client.get("/api/audit-log/?action=a.two").data["results"]

    assert all_actions == {"a.one", "a.two"}
    assert [row["action"] for row in filtered] == ["a.two"]


def test_audit_log_api_is_read_only(basic_client, org_a, make_org_member):
    owner = make_org_member(org_a, role=OWNER)

    response = basic_client(owner, org_slug=org_a.slug).post(
        "/api/audit-log/", {"action": "forged"}, format="json"
    )

    assert response.status_code == 405
