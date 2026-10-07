import pytest

from apps.projects.models import Project
from apps.projects.tests.factories import ProjectFactory
from apps.tenants.context import get_current_org, reset_current_org, set_current_org
from apps.tenants.exceptions import NoActiveTenantError
from apps.tenants.tests.factories import OrganizationFactory

pytestmark = pytest.mark.django_db


def test_default_manager_raises_with_no_active_tenant():
    ProjectFactory()  # exists in the DB regardless of context

    with pytest.raises(NoActiveTenantError):
        list(Project.objects.all())


def test_default_manager_filters_to_active_org():
    org_a = OrganizationFactory()
    org_b = OrganizationFactory()
    project_a = ProjectFactory(organization=org_a)
    ProjectFactory(organization=org_b)

    token = set_current_org(org_a)
    try:
        visible_ids = set(Project.objects.values_list("id", flat=True))
    finally:
        reset_current_org(token)

    assert visible_ids == {project_a.id}


def test_save_auto_assigns_active_org_on_create():
    org = OrganizationFactory()
    # Created before the tenant is active: ProjectFactory() writes a project
    # into a *different* org, which the save() guard rejects while `org` is
    # active (see test_save_guards.py).
    creator = ProjectFactory().created_by
    token = set_current_org(org)
    try:
        project = Project.objects.create(name="Autoassigned", created_by=creator)
    finally:
        reset_current_org(token)

    assert project.organization_id == org.id


def test_save_raises_when_creating_without_org_or_context():
    org = OrganizationFactory()
    project = Project(name="No org", organization_id=None, created_by=ProjectFactory(organization=org).created_by)

    assert get_current_org() is None
    with pytest.raises(NoActiveTenantError):
        project.save()


def test_all_tenants_manager_bypasses_filtering():
    org_a = OrganizationFactory()
    org_b = OrganizationFactory()
    ProjectFactory(organization=org_a)
    ProjectFactory(organization=org_b)

    # No active tenant is set, yet all_tenants must not raise or filter.
    assert get_current_org() is None
    assert Project.all_tenants.count() == 2
