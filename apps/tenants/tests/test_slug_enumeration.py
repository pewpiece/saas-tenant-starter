"""D-01: the API must not reveal whether an organization slug exists.

A non-member asking about a real org and anyone asking about a made-up org
must get byte-identical responses (status, headers and body), whatever
authentication method they use.
"""

import pytest

from apps.projects.tests.factories import ProjectFactory

pytestmark = pytest.mark.django_db

MISSING_SLUG = "no-such-org"


def _requests(project_id):
    return [
        ("get", "/api/projects/", None),
        ("get", f"/api/projects/{project_id}/", None),
        ("post", "/api/projects/", {"name": "x"}),
    ]


def _assert_identical(a, b):
    assert a.status_code == b.status_code
    assert dict(a.headers) == dict(b.headers)
    assert a.content == b.content


@pytest.mark.parametrize("index", [0, 1, 2], ids=["list", "detail", "create"])
def test_basic_auth_nonmember_cannot_distinguish_real_slug(
    basic_client, org_a, org_b, make_org_member, index
):
    outsider = make_org_member(org_b)
    project = ProjectFactory(organization=org_a)
    method, url, body = _requests(project.id)[index]

    real = getattr(basic_client(outsider, org_slug=org_a.slug), method)(url, body, format="json")
    fake = getattr(basic_client(outsider, org_slug=MISSING_SLUG), method)(url, body, format="json")

    assert real.status_code == 403
    _assert_identical(real, fake)


@pytest.mark.parametrize("index", [0, 1, 2], ids=["list", "detail", "create"])
def test_session_auth_nonmember_cannot_distinguish_real_slug(
    session_client, org_a, org_b, make_org_member, index
):
    outsider = make_org_member(org_b)
    project = ProjectFactory(organization=org_a)
    method, url, body = _requests(project.id)[index]

    real = getattr(session_client(outsider, org_slug=org_a.slug), method)(url, body, format="json")
    fake = getattr(session_client(outsider, org_slug=MISSING_SLUG), method)(url, body, format="json")

    assert real.status_code == 403
    _assert_identical(real, fake)


def test_anonymous_cannot_distinguish_real_slug(api_client, org_a):
    real = api_client.get("/api/projects/", HTTP_X_ORG=org_a.slug)
    fake = api_client.get("/api/projects/", HTTP_X_ORG=MISSING_SLUG)

    _assert_identical(real, fake)


def test_wrong_password_cannot_distinguish_real_slug(basic_client, org_a, make_org_member):
    member = make_org_member(org_a)

    real = basic_client(member, org_slug=org_a.slug, password="wrong").get("/api/projects/")
    fake = basic_client(member, org_slug=MISSING_SLUG, password="wrong").get("/api/projects/")

    _assert_identical(real, fake)
