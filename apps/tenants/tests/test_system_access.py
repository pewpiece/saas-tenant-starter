"""D-05: system code needs a safe, explicit way in, without weakening `objects`.

`all_tenants` must stay a non-default escape hatch: reverse relations are
built from the default manager, so they must keep failing closed outside a
tenant and stay scoped inside one.
"""

import io
import json

import pytest
from django.core.management import call_command

from apps.accounts.tests.factories import UserFactory
from apps.projects.models import Project
from apps.projects.tests.factories import ProjectFactory
from apps.tenants import context
from apps.tenants.context import get_current_org
from apps.tenants.exceptions import NoActiveTenantError
from apps.tenants.tests.factories import MembershipFactory

pytestmark = pytest.mark.django_db


def test_tenant_context_scopes_queries_and_resets(org_a, org_b):
    mine = ProjectFactory(organization=org_a)
    ProjectFactory(organization=org_b)

    with context.tenant_context(org_a):
        ids = set(Project.objects.values_list("id", flat=True))

    assert ids == {mine.id}
    assert get_current_org() is None


def test_tenant_context_resets_after_exception(org_a):
    with pytest.raises(ValueError), context.tenant_context(org_a):
        raise ValueError("boom")

    assert get_current_org() is None


def test_tenant_context_nests_and_restores_outer(org_a, org_b):
    with context.tenant_context(org_a):
        with context.tenant_context(org_b):
            assert get_current_org() == org_b
        assert get_current_org() == org_a
    assert get_current_org() is None


def test_all_tenants_is_not_the_default_manager():
    assert Project._meta.default_manager.name == "objects"
    assert Project._default_manager is Project.objects


def test_reverse_relation_inside_tenant_context_never_leaks(org_a, org_b):
    user = UserFactory()
    MembershipFactory(user=user, organization=org_a)
    MembershipFactory(user=user, organization=org_b)
    ProjectFactory(organization=org_a, created_by=user, name="in-a")
    ProjectFactory(organization=org_b, created_by=user, name="in-b")

    with context.tenant_context(org_a):
        names = set(user.projects.values_list("name", flat=True))
        org_b_projects = list(org_b.project_set.all())

    assert names == {"in-a"}
    assert org_b_projects == []


def test_reverse_relation_outside_tenant_context_fails_closed(org_a):
    user = UserFactory()
    ProjectFactory(organization=org_a, created_by=user)

    with pytest.raises(NoActiveTenantError):
        list(user.projects.all())


def test_dumpdata_works_without_a_request(org_a, org_b):
    ProjectFactory(organization=org_a, name="in-a")
    ProjectFactory(organization=org_b, name="in-b")
    out = io.StringIO()

    call_command("dumpdata", "projects", stdout=out)

    names = {row["fields"]["name"] for row in json.loads(out.getvalue())}
    assert names == {"in-a", "in-b"}


def test_dumpdata_org_option_exports_one_tenant(org_a, org_b):
    ProjectFactory(organization=org_a, name="in-a")
    ProjectFactory(organization=org_b, name="in-b")
    out = io.StringIO()

    call_command("dumpdata", "projects", org=org_a.slug, stdout=out)

    names = {row["fields"]["name"] for row in json.loads(out.getvalue())}
    assert names == {"in-a"}
