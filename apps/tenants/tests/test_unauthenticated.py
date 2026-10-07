"""D-09: unauthenticated requests get 401 with a WWW-Authenticate challenge.

Authentication must be checked before tenant resolution, so a request with
no credentials is told to authenticate (401) rather than being told about
the X-Org header (400) or refused outright (403).
"""

import pytest

pytestmark = pytest.mark.django_db


def test_anonymous_with_header_gets_401_challenge(api_client, org_a):
    response = api_client.get("/api/projects/", HTTP_X_ORG=org_a.slug)

    assert response.status_code == 401
    assert response["WWW-Authenticate"].startswith("Basic")


def test_anonymous_without_header_gets_401_not_400(api_client):
    response = api_client.get("/api/projects/")

    assert response.status_code == 401
    assert response["WWW-Authenticate"].startswith("Basic")


def test_wrong_password_gets_401_challenge(basic_client, org_a, make_org_member):
    member = make_org_member(org_a)

    response = basic_client(member, org_slug=org_a.slug, password="wrong").get("/api/projects/")

    assert response.status_code == 401
    assert response["WWW-Authenticate"].startswith("Basic")


def test_authenticated_without_header_gets_400(basic_client, org_a, make_org_member):
    member = make_org_member(org_a)

    response = basic_client(member).get("/api/projects/")

    assert response.status_code == 400
