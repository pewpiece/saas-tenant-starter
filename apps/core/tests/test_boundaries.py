"""Boundary values and error guessing across the API.

Plan limits, invitation expiry/reuse, last-owner, downgrade and org
switching boundaries live next to their features (test_plans.py,
test_invitations.py, test_members.py, test_org_switching.py); this module
adds the cross-cutting ones. Every case must answer 4xx, never 500.
"""

import re

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.projects.models import Project
from apps.projects.tests.factories import ProjectFactory
from apps.tenants.models import Membership

pytestmark = pytest.mark.django_db

OWNER = Membership.Role.OWNER


@pytest.fixture
def owner_client(basic_client, org_a, make_org_member):
    return basic_client(make_org_member(org_a, role=OWNER), org_slug=org_a.slug)


# --- Free plan members: 3 allowed, 4th refused (end to end through invites) ---------


def test_third_member_joins_fourth_is_refused(
    basic_client, api_client, org_a, make_org_member, django_capture_on_commit_callbacks, mailoutbox
):
    owner = make_org_member(org_a, role=OWNER)
    make_org_member(org_a)  # 2 members
    client = basic_client(owner, org_slug=org_a.slug)

    with django_capture_on_commit_callbacks(execute=True):
        third = client.post("/api/invitations/", {"email": "third@example.com"}, format="json")
    token = re.search(r"token=([\w-]+)", mailoutbox[-1].body).group(1)
    joined = api_client.post(
        "/api/invitations/accept/", {"token": token, "password": "Third-Member-91"}, format="json"
    )
    fourth = client.post("/api/invitations/", {"email": "fourth@example.com"}, format="json")

    assert (third.status_code, joined.status_code, fourth.status_code) == (201, 200, 403)
    assert Membership.objects.filter(organization=org_a).count() == 3


# --- Field lengths ------------------------------------------------------------------


@pytest.mark.parametrize("length, status", [(1, 201), (255, 201), (256, 400)])
def test_project_name_length(owner_client, length, status):
    response = owner_client.post("/api/projects/", {"name": "n" * length}, format="json")

    assert response.status_code == status


def test_project_name_cannot_be_blank(owner_client):
    assert owner_client.post("/api/projects/", {"name": ""}, format="json").status_code == 400


@pytest.mark.parametrize("slug_length, status", [(50, 201), (51, 400)])
def test_signup_slug_length(api_client, slug_length, status):
    response = api_client.post(
        "/api/auth/signup/",
        {
            "email": f"s{slug_length}@example.com",
            "password": "Long-Enough-Pass-7",
            "organization_name": "x",
            "organization_slug": "s" * slug_length,
        },
        format="json",
    )

    assert response.status_code == status


@pytest.mark.parametrize("local_length, status", [(64, 201), (65, 400)])
def test_invitation_email_local_part_length(owner_client, local_length, status):
    email = "a" * local_length + "@example.com"

    response = owner_client.post("/api/invitations/", {"email": email}, format="json")

    assert response.status_code == status


@pytest.mark.parametrize("email", ["not-an-email", "a@", "@b.com", "a b@c.com", ""])
def test_invalid_invitation_emails(owner_client, email):
    assert owner_client.post("/api/invitations/", {"email": email}, format="json").status_code == 400


@pytest.mark.parametrize("role", ["Owner", "OWNER", "superadmin", "", None])
def test_invalid_invitation_roles(owner_client, role):
    response = owner_client.post(
        "/api/invitations/", {"email": "r@example.com", "role": role}, format="json"
    )

    assert response.status_code == 400


# --- Pagination ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "query, status, rows",
    [
        ("?page_size=1", 200, 1),
        ("?page_size=100", 200, 25),
        ("?page_size=0", 200, 20),
        ("?page_size=-1", 200, 20),
        ("?page_size=abc", 200, 20),
        ("?page=2", 200, 5),
        ("?page=3", 404, None),
        ("?page=0", 404, None),
        ("?page=last", 200, 5),
    ],
)
def test_pagination_edges(basic_client, org_a, make_org_member, query, status, rows):
    user = make_org_member(org_a)
    ProjectFactory.create_batch(25, organization=org_a, created_by=user)

    response = basic_client(user, org_slug=org_a.slug).get("/api/projects/" + query)

    assert response.status_code == status
    if rows is not None:
        assert len(response.data["results"]) == rows


# --- X-Org header error guessing -----------------------------------------------------


@pytest.mark.parametrize(
    "header",
    [" org-a", "org-a ", "ORG-A", "org-a,org-b", "org_a", "org-a\t", "ørg-a", "x" * 5000, "%00", "' OR 1=1 --"],
)
def test_malformed_org_headers_are_refused_identically(basic_client, org_a, make_org_member, header):
    user = make_org_member(org_a)

    odd = basic_client(user, org_slug=header).get("/api/projects/")
    unknown = basic_client(user, org_slug="no-such-org").get("/api/projects/")

    assert odd.status_code == 403
    assert odd.content == unknown.content


# --- Malformed bodies --------------------------------------------------------------


@pytest.mark.parametrize(
    "body, content_type",
    [
        ("{not json", "application/json"),
        ("[]", "application/json"),
        ('"just a string"', "application/json"),
        ("name=x", "text/plain"),
    ],
)
def test_malformed_bodies_are_4xx(owner_client, body, content_type):
    response = owner_client.generic("POST", "/api/projects/", body, content_type=content_type)

    assert 400 <= response.status_code < 500
    assert not Project.all_tenants.exists()


@pytest.mark.parametrize("value", [None, 123, ["x"], {"a": 1}, True])
def test_wrong_types_for_project_name(owner_client, value):
    response = owner_client.post("/api/projects/", {"name": value}, format="json")

    assert response.status_code in (201, 400)  # DRF coerces 123 -> "123"
    if response.status_code == 201:
        assert isinstance(Project.all_tenants.get().name, str)


def test_non_integer_ids_are_404(owner_client):
    for url in ["/api/projects/abc/", "/api/members/1.5/", "/api/invitations/-1/"]:
        assert owner_client.get(url).status_code == 404


def test_huge_id_is_404_not_500(owner_client):
    assert owner_client.get(f"/api/projects/{2**70}/").status_code == 404


# --- Credentials error guessing ------------------------------------------------------


@pytest.mark.parametrize(
    "authorization",
    ["Basic", "Basic !!!notbase64", "Basic " + "QQ==", "Bearer abc", "Basic " + "x" * 10000],
)
def test_malformed_authorization_headers_are_401(api_client, org_a, authorization):
    response = api_client.get("/api/projects/", HTTP_AUTHORIZATION=authorization, HTTP_X_ORG="org-a")

    assert response.status_code == 401


def test_inactive_user_is_refused(basic_client, org_a, make_org_member):
    user = make_org_member(org_a)
    user.is_active = False
    user.save()

    assert basic_client(user, org_slug=org_a.slug).get("/api/projects/").status_code == 401


def test_password_is_case_sensitive(basic_client, org_a, make_org_member):
    user = make_org_member(org_a)

    response = basic_client(user, org_slug=org_a.slug, password="TESTPASS123").get("/api/projects/")

    assert response.status_code == 401


def test_email_login_is_case_sensitive_for_local_part(basic_client, org_a):
    user = UserFactory(email="Case@example.com")
    Membership.objects.create(user=user, organization=org_a)

    exact = basic_client(email="Case@example.com", org_slug="org-a").get("/api/projects/")
    other = basic_client(email="case@example.com", org_slug="org-a").get("/api/projects/")

    assert (exact.status_code, other.status_code) == (200, 401)


# --- ZAP SQL-injection alerts (40018), replayed without throttling ---------------------
# ZAP's boolean-based heuristic flagged signup/accept while the "auth" throttle
# was flipping responses to 429 mid-scan. The same true/false payload pairs
# must produce identical responses: the input never reaches SQL as code.


@pytest.mark.parametrize(
    "field, true_payload, false_payload",
    [
        ("email", "zaproxy@example.com AND 1=1 -- ", "zaproxy@example.com AND 1=2 -- "),
        ("organization_slug", "John Doe' AND '1'='1' -- ", "John Doe' AND '1'='2' -- "),
        ("organization_name", "x' OR '1'='1", "x' OR '1'='2"),
    ],
)
def test_signup_sql_boolean_payloads_behave_identically(api_client, field, true_payload, false_payload):
    def send(value):
        body = {"email": "sqli@example.com", "password": "Sqli-Check-Pass-1", "organization_name": "S"}
        body[field] = value
        return api_client.post("/api/auth/signup/", body, format="json")

    true_response = send(true_payload)
    from apps.accounts.models import User
    from apps.tenants.models import Organization

    Organization.objects.all().delete()  # first: users who own an org cannot be deleted
    User.objects.all().delete()
    false_response = send(false_payload)

    assert true_response.status_code == false_response.status_code
    assert true_response.status_code in (201, 400)
    if true_response.status_code == 400:
        assert true_response.data.keys() == false_response.data.keys()


@pytest.mark.parametrize("value", ["John Doe AND 1=1 -- ", "John Doe AND 1=2 -- "])
def test_accept_sql_boolean_payloads_are_plain_data(api_client, value):
    response = api_client.post(
        "/api/invitations/accept/", {"token": "nope", "password": "x", "first_name": value}, format="json"
    )

    assert response.status_code == 400
    assert list(response.data) == ["token"]
