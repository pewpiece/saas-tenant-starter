import io

import pytest
from django.core.management import call_command

from apps.billing.models import Subscription
from apps.projects.models import Project
from apps.tenants.models import Membership

pytestmark = pytest.mark.django_db


def test_seed_qa_is_idempotent_and_isolated():
    for _ in range(2):
        call_command("seed_qa", tenants=3, projects=4, stdout=io.StringIO())

    assert Membership.objects.filter(role="owner", organization__slug__startswith="qa-org-").count() == 3
    assert set(Subscription.objects.values_list("plan", flat=True)) == {"pro"}
    for n in range(3):
        rows = Project.all_tenants.filter(organization__slug=f"qa-org-{n}")
        assert rows.count() == 4
        assert set(rows.values_list("created_by__email", flat=True)) == {f"qa-owner-{n}@example.com"}
