"""D-03 and write-path probes: no ORM write may put a row in another tenant.

D-03 covers TenantOwnedModel.save(). The probes check the ORM paths that skip
save(): bulk_create, QuerySet.update and Manager.raw.
"""

from contextlib import contextmanager

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.projects.models import Project
from apps.projects.tests.factories import ProjectFactory
from apps.tenants import exceptions
from apps.tenants.context import reset_current_org, set_current_org

pytestmark = pytest.mark.django_db


@contextmanager
def active(org):
    token = set_current_org(org)
    try:
        yield
    finally:
        reset_current_org(token)


# --- D-03: save() ----------------------------------------------------------


def test_create_with_other_org_under_active_tenant_is_rejected(org_a, org_b):
    user = UserFactory()

    with active(org_a), pytest.raises(exceptions.TenantMismatchError):
        Project.objects.create(name="planted", organization=org_b, created_by=user)

    assert not Project.all_tenants.filter(organization=org_b).exists()


def test_update_moving_row_to_other_org_under_active_tenant_is_rejected(org_a, org_b):
    project = ProjectFactory(organization=org_a)

    with active(org_a):
        project = Project.objects.get(pk=project.pk)
        project.organization = org_b
        with pytest.raises(exceptions.TenantMismatchError):
            project.save()

    assert Project.all_tenants.get(pk=project.pk).organization_id == org_a.id


def test_update_moving_row_to_other_org_without_tenant_is_rejected(org_a, org_b):
    project = Project.all_tenants.get(pk=ProjectFactory(organization=org_a).pk)

    project.organization = org_b
    with pytest.raises(exceptions.TenantMismatchError):
        project.save()

    assert Project.all_tenants.get(pk=project.pk).organization_id == org_a.id


def test_update_of_row_from_other_org_under_active_tenant_is_rejected(org_a, org_b):
    other = Project.all_tenants.get(pk=ProjectFactory(organization=org_b).pk)

    with active(org_a):
        other.name = "renamed from the wrong tenant"
        with pytest.raises(exceptions.TenantMismatchError):
            other.save()

    assert Project.all_tenants.get(pk=other.pk).name != "renamed from the wrong tenant"


def test_delete_of_row_from_other_org_under_active_tenant_is_rejected(org_a, org_b):
    other = Project.all_tenants.get(pk=ProjectFactory(organization=org_b).pk)

    with active(org_a), pytest.raises(exceptions.TenantMismatchError):
        other.delete()

    assert Project.all_tenants.filter(pk=other.pk).exists()


def test_normal_create_and_update_still_work(org_a):
    user = UserFactory()

    with active(org_a):
        project = Project.objects.create(name="ok", created_by=user)
        project.name = "still ok"
        project.save()

    assert Project.all_tenants.get(pk=project.pk).name == "still ok"
    assert project.organization_id == org_a.id


def test_system_code_can_create_with_explicit_org_and_no_tenant(org_a):
    project = Project.all_tenants.create(name="seeded", organization=org_a, created_by=UserFactory())

    assert project.organization_id == org_a.id


# --- Probe: bulk_create ------------------------------------------------------


def test_bulk_create_cannot_write_into_other_org(org_a, org_b):
    user = UserFactory()

    with active(org_a), pytest.raises(exceptions.TenantMismatchError):
        Project.objects.bulk_create([Project(name="planted", organization=org_b, created_by=user)])

    assert not Project.all_tenants.filter(organization=org_b).exists()


def test_bulk_create_assigns_active_org(org_a):
    user = UserFactory()

    with active(org_a):
        Project.objects.bulk_create([Project(name="bulk", created_by=user)])

    assert Project.all_tenants.get(name="bulk").organization_id == org_a.id


# --- Probe: QuerySet.update -------------------------------------------------


@pytest.mark.parametrize("field", ["organization", "organization_id"])
def test_queryset_update_cannot_move_rows_to_other_org(org_a, org_b, field):
    project = ProjectFactory(organization=org_a)
    value = org_b if field == "organization" else org_b.id

    with active(org_a), pytest.raises(exceptions.TenantMismatchError):
        Project.objects.filter(pk=project.pk).update(**{field: value})

    assert Project.all_tenants.get(pk=project.pk).organization_id == org_a.id


def test_queryset_update_of_other_fields_stays_scoped(org_a, org_b):
    mine = ProjectFactory(organization=org_a, name="mine")
    theirs = ProjectFactory(organization=org_b, name="theirs")

    with active(org_a):
        Project.objects.update(name="bulk renamed")

    assert Project.all_tenants.get(pk=mine.pk).name == "bulk renamed"
    assert Project.all_tenants.get(pk=theirs.pk).name == "theirs"


# --- Probe: raw() -----------------------------------------------------------


def test_raw_on_tenant_manager_is_refused(org_a, org_b):
    ProjectFactory(organization=org_b, name="theirs")

    with active(org_a), pytest.raises(exceptions.UnscopedQueryError):
        list(Project.objects.raw("SELECT * FROM projects_project"))
