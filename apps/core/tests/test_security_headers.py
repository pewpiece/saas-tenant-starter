"""Browser hardening headers on every response (D-20)."""

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("path", ["/api/me/", "/api/schema/", "/api/docs/", "/admin/login/", "/nope/"])
def test_every_response_has_the_hardening_headers(path):
    response = Client().get(path)

    assert "Content-Security-Policy" in response
    assert response["Permissions-Policy"].startswith("accelerometer=()")
    assert response["Cross-Origin-Embedder-Policy"] == "credentialless"
    if path != "/api/docs/":  # drf-spectacular sets its own COOP on the Swagger page
        assert response["Cross-Origin-Opener-Policy"] == "same-origin"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in response["Content-Security-Policy"]


def test_api_policy_allows_nothing():
    csp = Client().get("/api/me/")["Content-Security-Policy"]

    assert csp.startswith("default-src 'none'")


def test_admin_policy_forbids_scripts_from_anywhere_but_self():
    csp = Client().get("/admin/login/")["Content-Security-Policy"]

    assert "script-src" not in csp  # falls back to default-src 'self'
    assert "'unsafe-inline'" not in csp.split("style-src")[0]
    assert "default-src 'self'" in csp


def test_only_the_docs_page_may_run_inline_scripts_and_use_the_cdn():
    docs = Client().get("/api/docs/")["Content-Security-Policy"]
    admin = Client().get("/admin/login/")["Content-Security-Policy"]
    api = Client().get("/api/me/")["Content-Security-Policy"]

    assert "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net" in docs
    assert "cdn.jsdelivr.net" not in admin
    assert "cdn.jsdelivr.net" not in api


def test_swagger_page_only_needs_what_the_policy_allows():
    """Guards against the template growing a source the docs CSP does not list."""
    html = Client().get("/api/docs/").content.decode()

    assert "https://cdn.jsdelivr.net" in html
    assert html.count("<script") == html.count("<script src=") + 1  # one inline script


def test_a_view_can_override_the_policy(rf):
    from django.http import HttpResponse

    from apps.core.middleware import SecurityHeadersMiddleware

    mw = SecurityHeadersMiddleware(lambda r: HttpResponse(headers={"Content-Security-Policy": "custom"}))

    assert mw(rf.get("/api/me/"))["Content-Security-Policy"] == "custom"
