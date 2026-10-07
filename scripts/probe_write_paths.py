"""Probe ORM write/read paths that skip TenantOwnedModel.save() or the
tenant-filtered queryset. Run with:

    python manage.py shell < scripts/probe_write_paths.py

Everything runs inside a transaction that is rolled back, so it leaves no
data behind. Each probe prints what actually happened.
"""

from django.db import transaction

from apps.accounts.models import User
from apps.projects.models import Project
from apps.tenants.context import reset_current_org, set_current_org
from apps.tenants.models import Organization


class _Rollback(Exception):
    pass


def probe(name, fn, org):
    token = set_current_org(org)
    try:
        with transaction.atomic():
            result = fn()
            print(f"{name}: {result}")
            raise _Rollback
    except _Rollback:
        pass
    except Exception as exc:  # noqa: BLE001 - reporting whatever happens is the point
        print(f"{name}: raised {type(exc).__name__}: {str(exc)[:90]}")
    finally:
        reset_current_org(token)


with transaction.atomic():
    a = Organization.objects.create(slug="probe-a", name="Probe A")
    b = Organization.objects.create(slug="probe-b", name="Probe B")
    user = User.objects.create_user("probe@example.com", "x")
    pa = Project.all_tenants.create(name="row-in-a", organization=a, created_by=user)
    Project.all_tenants.create(name="row-in-b", organization=b, created_by=user)

    probe(
        "bulk_create(organization=b) with tenant a active -> rows written to",
        lambda: [
            p.organization.slug
            for p in Project.objects.bulk_create(
                [Project(name="x", organization=b, created_by=user)]
            )
        ],
        a,
    )
    probe(
        "bulk_create(no organization) with tenant a active",
        lambda: Project.objects.bulk_create([Project(name="y", created_by=user)]),
        a,
    )
    probe(
        "objects.filter(pk=row-in-a).update(organization=b) -> row now in",
        lambda: (
            Project.objects.filter(pk=pa.pk).update(organization=b),
            Project.all_tenants.get(pk=pa.pk).organization.slug,
        ),
        a,
    )
    probe(
        "objects.raw('SELECT * FROM projects_project') with tenant a -> rows seen",
        lambda: sorted(p.name for p in Project.objects.raw("SELECT * FROM projects_project")),
        a,
    )
    transaction.set_rollback(True)
