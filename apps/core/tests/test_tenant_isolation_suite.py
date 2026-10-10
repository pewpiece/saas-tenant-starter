"""Generated tenant-isolation (IDOR) suite.

Every route under /api/ is discovered from the URLconf. Each tenant-scoped
route is attacked with every HTTP method it serves, by an *owner* of org A
(the most privileged outsider to org B):

  1. detail routes with org B's object ids, under X-Org: org-a -> 404
  2. collection routes (list, search, filter, export, create, plan change)
     under X-Org: org-a, with bodies and query strings naming org B
  3. any route under X-Org: org-b (not a member) -> the same 403 as an
     unknown slug

After every request, org B's data must be unchanged and none of org B's
secret strings may appear in the response. Positive controls check that the
same harness does reach org A's own objects, so the suite cannot pass
vacuously. A new /api/ route fails `test_every_api_route_is_classified`
until it is declared tenant-scoped (with a fixture) or public.
"""

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditLogEntry
from apps.audit.services import record
from apps.billing.models import Subscription
from apps.core.tests.routes import api_routes
from apps.projects.models import Project
from apps.projects.tests.factories import ProjectFactory
from apps.tenants.context import tenant_context
from apps.tenants.models import Invitation, Membership
from apps.tenants.tests.factories import MembershipFactory, OrganizationFactory

pytestmark = pytest.mark.django_db

ROUTES = api_routes()

PUBLIC_ROUTES = {
    "api/auth/token/",
    "api/auth/signup/",
    "api/me/",
    "api/invitations/accept/",
    "api/schema/",
    "api/docs/",
}

# How to find org B's (victim) and org A's (attacker) object for each tenant
# detail route.
DETAIL_OBJECTS = {
    "api/projects/{pk}/": "project",
    "api/members/{pk}/": "membership",
    "api/invitations/{pk}/": "invitation",
}

SECRETS = [
    b"B-SECRET-PROJECT",
    b"b-member-secret@victim.test",
    b"b-invite-secret@victim.test",
    b"b-owner-secret@victim.test",
    b"B-SECRET-AUDIT",
]

GET_QUERIES = [
    "",
    "?page_size=100",
    "?page=2",
    "?action=project.create",
    "?search=B-SECRET",
    "?organization=org-b",
    "?organization_id={b_id}",
]


def _body(world):
    b = world["org_b"]
    return {
        "name": "probe",
        "description": "probe",
        "email": "probe@attacker.test",
        "role": "member",
        "plan": "pro",
        "organization": b.slug,
        "organization_id": b.id,
        "user": world["b_owner"].id,
    }


def _snapshot(org):
    return {
        "projects": sorted(
            Project.all_tenants.filter(organization=org).values_list("id", "name", "description")
        ),
        "memberships": sorted(
            Membership.objects.filter(organization=org).values_list("id", "user_id", "role")
        ),
        "invitations": sorted(
            (i.id, i.email, i.role, i.status) for i in Invitation.all_tenants.filter(organization=org)
        ),
        "plan": Subscription.objects.get(organization=org).plan,
        "audit": AuditLogEntry.all_tenants.filter(organization=org).count(),
    }


@pytest.fixture
def world():
    org_a = OrganizationFactory(slug="org-a", name="Org A")
    org_b = OrganizationFactory(slug="org-b", name="Org B")
    for org in (org_a, org_b):
        Subscription.objects.create(organization=org, plan="pro")

    attacker = UserFactory(email="attacker@attacker.test")
    MembershipFactory(user=attacker, organization=org_a, role=Membership.Role.OWNER)
    a_member = MembershipFactory(organization=org_a, role=Membership.Role.MEMBER)
    a_project = ProjectFactory(organization=org_a, name="a-project", created_by=attacker)

    b_owner = UserFactory(email="b-owner-secret@victim.test")
    MembershipFactory(user=b_owner, organization=org_b, role=Membership.Role.OWNER)
    b_member = MembershipFactory(
        user=UserFactory(email="b-member-secret@victim.test"),
        organization=org_b,
        role=Membership.Role.MEMBER,
    )
    b_project = ProjectFactory(organization=org_b, name="B-SECRET-PROJECT", created_by=b_owner)

    with tenant_context(org_a):
        a_invitation, _ = Invitation.issue(email="a-invite@a.test", role="member", invited_by=attacker)
    with tenant_context(org_b):
        b_invitation, _ = Invitation.issue(
            email="b-invite-secret@victim.test", role="member", invited_by=b_owner
        )
        record("project.create", actor=b_owner, target=b_project, changes={"note": "B-SECRET-AUDIT"})

    return {
        "org_a": org_a,
        "org_b": org_b,
        "attacker": attacker,
        "b_owner": b_owner,
        "objects": {
            "a": {"project": a_project, "membership": a_member, "invitation": a_invitation},
            "b": {"project": b_project, "membership": b_member, "invitation": b_invitation},
        },
    }


def _request(client, method, url, world):
    if method in ("get", "delete"):
        return getattr(client, method)(url)
    return getattr(client, method)(url, _body(world), format="json")


def _assert_no_leak(response, world, before):
    for secret in SECRETS:
        assert secret not in response.content, f"{secret!r} leaked: {response.content[:300]!r}"
    assert _snapshot(world["org_b"]) == before, "org B's data changed"


def _cases(detail):
    return [
        pytest.param(route, method, id=f"{method.upper()} {route}")
        for route in ROUTES
        if route.is_tenant_scoped and route.is_detail == detail
        for method in route.methods
    ]


@pytest.mark.parametrize("route, method", _cases(detail=True))
def test_detail_route_hides_other_orgs_objects(basic_client, world, route, method):
    client = basic_client(world["attacker"], org_slug="org-a")
    victim = world["objects"]["b"][DETAIL_OBJECTS[route.pattern]]
    before = _snapshot(world["org_b"])

    response = _request(client, method, route.url(victim.pk), world)

    assert response.status_code in (404, 405), response.content[:300]
    _assert_no_leak(response, world, before)


@pytest.mark.parametrize("route, method", _cases(detail=False))
def test_collection_route_never_leaks_other_org(basic_client, world, route, method):
    client = basic_client(world["attacker"], org_slug="org-a")
    before = _snapshot(world["org_b"])
    queries = GET_QUERIES if method == "get" else [""]

    for query in queries:
        url = route.url() + query.format(b_id=world["org_b"].id)
        response = _request(client, method, url, world)

        assert response.status_code < 500, (url, response.content[:300])
        _assert_no_leak(response, world, before)


@pytest.mark.parametrize("route, method", _cases(detail=True) + _cases(detail=False))
def test_foreign_org_header_is_refused_like_unknown_slug(basic_client, world, route, method):
    victim = world["objects"]["b"].get(DETAIL_OBJECTS.get(route.pattern, ""))
    url = route.url(victim.pk if victim else None)
    before = _snapshot(world["org_b"])

    foreign = _request(basic_client(world["attacker"], org_slug="org-b"), method, url, world)
    unknown = _request(basic_client(world["attacker"], org_slug="no-such-org"), method, url, world)

    assert foreign.status_code == 403
    assert (foreign.content, dict(foreign.headers)) == (unknown.content, dict(unknown.headers))
    _assert_no_leak(foreign, world, before)


@pytest.mark.parametrize(
    "route",
    [pytest.param(r, id=str(r)) for r in ROUTES if r.is_tenant_scoped and r.is_detail],
)
def test_positive_control_own_objects_are_reachable(basic_client, world, route):
    client = basic_client(world["attacker"], org_slug="org-a")
    own = world["objects"]["a"][DETAIL_OBJECTS[route.pattern]]

    response = client.get(route.url(own.pk))

    assert response.status_code == 200


def test_positive_control_lists_show_own_data(basic_client, world):
    client = basic_client(world["attacker"], org_slug="org-a")

    assert b"a-project" in client.get("/api/projects/").content
    assert b"a-invite@a.test" in client.get("/api/invitations/").content
    assert b"attacker@attacker.test" in client.get("/api/members/").content


def test_every_api_route_is_classified():
    tenant_detail = {r.pattern for r in ROUTES if r.is_tenant_scoped and r.is_detail}
    public = {r.pattern for r in ROUTES if not r.is_tenant_scoped}

    assert public == PUBLIC_ROUTES, "new public route: add it to PUBLIC_ROUTES deliberately"
    assert tenant_detail == set(DETAIL_OBJECTS), "new tenant detail route: add a fixture object"


def test_suite_covers_a_meaningful_number_of_cases():
    # Guard against the discovery silently finding nothing.
    assert len(_cases(detail=True)) >= 9
    assert len(_cases(detail=False)) >= 8
