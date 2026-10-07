import pytest

from apps.projects.views import ProjectViewSet
from apps.tenants.context import get_current_org
from apps.tenants.models import Membership

pytestmark = pytest.mark.django_db


def test_missing_x_org_header_is_rejected(api_client, django_user_model, org_a):
    user = django_user_model.objects.create_user(email="u@example.com", password="pw")
    api_client.force_authenticate(user=user)

    response = api_client.get("/api/projects/")

    assert response.status_code == 400


def test_unknown_org_slug_is_rejected(api_client, django_user_model):
    user = django_user_model.objects.create_user(email="u2@example.com", password="pw")
    api_client.force_authenticate(user=user)
    api_client.credentials(HTTP_X_ORG="does-not-exist")

    response = api_client.get("/api/projects/")

    assert response.status_code == 403


def test_user_without_membership_gets_403(api_client, django_user_model, org_a):
    user = django_user_model.objects.create_user(email="u3@example.com", password="pw")
    api_client.force_authenticate(user=user)
    api_client.credentials(HTTP_X_ORG=org_a.slug)

    response = api_client.get("/api/projects/")

    assert response.status_code == 403


def test_member_with_valid_header_is_allowed(api_client, org_a, make_org_member):
    user = make_org_member(org_a, role=Membership.Role.MEMBER)
    api_client.force_authenticate(user=user)
    api_client.credentials(HTTP_X_ORG=org_a.slug)

    response = api_client.get("/api/projects/")

    assert response.status_code == 200


# Ported from the Milestone 1 TenantMiddleware unit test: tenant resolution now
# lives in TenantScopedViewMixin, so the same guarantee (context is set during
# the request and reset afterwards) is checked through a real request.
def test_context_var_resets_after_request(api_client, org_a, make_org_member, monkeypatch):
    seen_during_request = {}
    original = ProjectViewSet.get_queryset

    def spy(self):
        seen_during_request["org"] = get_current_org()
        return original(self)

    monkeypatch.setattr(ProjectViewSet, "get_queryset", spy)
    user = make_org_member(org_a, role=Membership.Role.MEMBER)
    api_client.force_authenticate(user=user)
    api_client.credentials(HTTP_X_ORG=org_a.slug)

    assert get_current_org() is None
    api_client.get("/api/projects/")
    assert seen_during_request["org"] == org_a
    assert get_current_org() is None


def test_context_var_resets_when_view_raises(api_client, org_a, make_org_member, monkeypatch):
    def boom(self):
        raise RuntimeError("view crashed")

    monkeypatch.setattr(ProjectViewSet, "get_queryset", boom)
    user = make_org_member(org_a, role=Membership.Role.MEMBER)
    api_client.force_authenticate(user=user)
    api_client.credentials(HTTP_X_ORG=org_a.slug)

    with pytest.raises(RuntimeError):
        api_client.get("/api/projects/")
    assert get_current_org() is None


def test_context_var_does_not_leak_between_requests(api_client, org_a, org_b, make_org_member):
    user_a = make_org_member(org_a, role=Membership.Role.MEMBER)
    user_b = make_org_member(org_b, role=Membership.Role.MEMBER)

    api_client.force_authenticate(user=user_a)
    api_client.credentials(HTTP_X_ORG=org_a.slug)
    api_client.get("/api/projects/")
    assert get_current_org() is None

    api_client.force_authenticate(user=user_b)
    api_client.credentials(HTTP_X_ORG=org_b.slug)
    api_client.get("/api/projects/")
    assert get_current_org() is None
