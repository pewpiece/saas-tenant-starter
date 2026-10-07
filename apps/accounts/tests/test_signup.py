import pytest

from apps.accounts.models import User
from apps.audit.models import AuditLogEntry
from apps.billing.models import Subscription
from apps.tenants.models import Membership, Organization

pytestmark = pytest.mark.django_db

PASSWORD = "Correct-Horse-42"


def _signup(api_client, **overrides):
    body = {
        "email": "founder@example.com",
        "password": PASSWORD,
        "organization_name": "Founder Co",
    }
    body.update(overrides)
    return api_client.post("/api/auth/signup/", body, format="json")


def test_signup_creates_user_org_owner_membership_and_free_plan(api_client):
    response = _signup(api_client)

    assert response.status_code == 201
    user = User.objects.get(email="founder@example.com")
    org = Organization.objects.get(slug="founder-co")
    assert Membership.objects.get(user=user, organization=org).role == Membership.Role.OWNER
    assert Subscription.objects.get(organization=org).plan == "free"
    assert AuditLogEntry.all_tenants.filter(organization=org, action="organization.create").exists()
    assert response.data["organization"] == {"slug": "founder-co", "name": "Founder Co"}
    assert "password" not in response.data["user"]


def test_new_user_can_immediately_use_their_org(api_client, basic_client):
    _signup(api_client, organization_slug="my-co")
    user = User.objects.get(email="founder@example.com")

    response = basic_client(user, org_slug="my-co", password=PASSWORD).get("/api/projects/")

    assert response.status_code == 200


def test_duplicate_email_is_rejected_case_insensitively(api_client):
    _signup(api_client)

    response = _signup(api_client, email="FOUNDER@example.com", organization_name="Other")

    assert response.status_code == 400
    assert "email" in response.data
    assert User.objects.count() == 1


def test_taken_slug_is_rejected_and_nothing_is_created(api_client):
    Organization.objects.create(name="Taken", slug="taken")

    response = _signup(api_client, organization_slug="taken")

    assert response.status_code == 400
    assert not User.objects.filter(email="founder@example.com").exists()


@pytest.mark.parametrize("password", ["short", "12345678901", "founder@example.com", "password123"])
def test_weak_passwords_are_rejected(api_client, password):
    response = _signup(api_client, password=password)

    assert response.status_code == 400
    assert "password" in response.data
    assert not User.objects.exists()
    assert not Organization.objects.exists()


def test_unsluggable_org_name_requires_explicit_slug(api_client):
    response = _signup(api_client, organization_name="!!!")

    assert response.status_code == 400
    assert "organization_slug" in response.data


def test_privilege_fields_in_body_are_ignored(api_client):
    _signup(api_client, is_staff=True, is_superuser=True, role="member")
    user = User.objects.get(email="founder@example.com")

    assert not user.is_staff and not user.is_superuser
    assert user.memberships.get().role == Membership.Role.OWNER


def test_signup_ignores_credentials_and_needs_no_csrf(session_client, org_a, make_org_member):
    client = session_client(make_org_member(org_a), enforce_csrf_checks=True)

    response = _signup(client)

    assert response.status_code == 201


def test_me_lists_every_org_of_the_user(basic_client, org_a, org_b, make_org_member):
    user = make_org_member(org_a, role=Membership.Role.ADMIN)
    make_org_member(org_b, role=Membership.Role.MEMBER, user=user)

    response = basic_client(user).get("/api/me/")

    assert response.status_code == 200
    assert response.data["organizations"] == [
        {"slug": "org-a", "name": "Org A", "role": "admin"},
        {"slug": "org-b", "name": "Org B", "role": "member"},
    ]


def test_me_requires_authentication(api_client):
    assert api_client.get("/api/me/").status_code == 401
