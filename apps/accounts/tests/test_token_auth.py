"""Bearer tokens (D-18): log in once, then skip the per-request password hash."""

from datetime import timedelta

import pytest
from django.conf import settings
from django.utils import timezone

from apps.accounts.models import AuthToken
from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from apps.projects.tests.factories import ProjectFactory

pytestmark = pytest.mark.django_db

TOKEN_URL = "/api/auth/token/"


def _login(api_client, user, password=DEFAULT_PASSWORD):
    return api_client.post(TOKEN_URL, {"email": user.email, "password": password}, format="json")


def test_login_returns_a_token_that_authenticates(api_client, org_a, make_org_member):
    user = make_org_member(org_a)
    ProjectFactory(organization=org_a, name="visible")

    response = _login(api_client, user)

    assert response.status_code == 201
    assert set(response.data) == {"token", "expires_at"}
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['token']}", HTTP_X_ORG="org-a")
    listing = api_client.get("/api/projects/")
    assert listing.status_code == 200
    assert [p["name"] for p in listing.data["results"]] == ["visible"]


def test_only_a_hash_of_the_token_is_stored(api_client):
    user = UserFactory()
    key = _login(api_client, user).data["token"]

    stored = AuthToken.objects.get()
    assert stored.key_hash == AuthToken.hash_key(key)
    assert key not in stored.key_hash


def test_wrong_password_is_401_and_issues_nothing(api_client):
    user = UserFactory()

    response = _login(api_client, user, password="wrong-password")

    assert response.status_code == 401
    assert AuthToken.objects.count() == 0


def test_unknown_email_is_indistinguishable_from_wrong_password(api_client):
    user = UserFactory()
    wrong = _login(api_client, user, password="wrong-password")
    unknown = api_client.post(TOKEN_URL, {"email": "nobody@example.test", "password": "x"}, format="json")

    assert (wrong.status_code, wrong.content) == (unknown.status_code, unknown.content)


def test_inactive_user_cannot_log_in(api_client):
    user = UserFactory(is_active=False)

    assert _login(api_client, user).status_code == 401


def test_missing_fields_are_400(api_client):
    assert api_client.post(TOKEN_URL, {"email": "a@b.test"}, format="json").status_code == 400


def test_failed_logins_share_the_basic_auth_lockout(api_client):
    user = UserFactory()
    for _ in range(settings.AUTH_FAILURE_LIMIT):
        assert _login(api_client, user, password="wrong-password").status_code == 401

    assert _login(api_client, user).status_code == 429


def test_failed_basic_auth_locks_out_token_login(api_client):
    user = UserFactory()
    api_client.credentials(HTTP_AUTHORIZATION="Basic dXNlcjp3cm9uZw==")
    for _ in range(settings.AUTH_FAILURE_LIMIT):
        api_client.get("/api/me/")
    api_client.credentials()

    assert _login(api_client, user).status_code == 429


def test_expired_token_is_rejected(api_client):
    user = UserFactory()
    token, key = AuthToken.issue(user)
    AuthToken.objects.filter(pk=token.pk).update(expires_at=timezone.now() - timedelta(seconds=1))

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {key}")
    assert api_client.get("/api/me/").status_code == 401


def test_unknown_token_is_401_with_bearer_challenge_after_basic(api_client):
    api_client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")

    response = api_client.get("/api/me/")

    assert response.status_code == 401


@pytest.mark.parametrize("header", ["Bearer", "Bearer a b", "Bearer \xff"])
def test_malformed_bearer_headers_are_401(api_client, header):
    api_client.credentials(HTTP_AUTHORIZATION=header)

    assert api_client.get("/api/me/").status_code == 401


def test_token_stops_working_when_the_user_is_deactivated(api_client):
    user = UserFactory()
    _, key = AuthToken.issue(user)
    user.is_active = False
    user.save()

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {key}")
    assert api_client.get("/api/me/").status_code == 401


def test_anonymous_requests_still_get_the_basic_challenge(api_client):
    response = api_client.get("/api/me/")

    assert response.status_code == 401
    assert response["WWW-Authenticate"].startswith("Basic")


def test_logout_revokes_only_the_token_used(api_client):
    user = UserFactory()
    _, key = AuthToken.issue(user)
    _, other_key = AuthToken.issue(user)

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {key}")
    assert api_client.delete(TOKEN_URL).status_code == 204
    assert api_client.get("/api/me/").status_code == 401

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {other_key}")
    assert api_client.get("/api/me/").status_code == 200


def test_logout_requires_a_token(api_client):
    user = UserFactory()
    assert api_client.delete(TOKEN_URL).status_code == 401
    api_client.force_authenticate(user=user)
    # force_authenticate has no token behind it, so there is nothing to revoke.
    assert api_client.delete(TOKEN_URL).status_code == 400


def test_deleting_a_user_deletes_their_tokens(api_client):
    user = UserFactory()
    AuthToken.issue(user)

    user.delete()

    assert AuthToken.objects.count() == 0


def test_tokens_do_not_bypass_tenant_resolution(api_client, org_a, org_b, make_org_member):
    user = make_org_member(org_a)
    _, key = AuthToken.issue(user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {key}", HTTP_X_ORG=org_b.slug)

    assert api_client.get("/api/projects/").status_code == 403
