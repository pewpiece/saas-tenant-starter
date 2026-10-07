from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import User
from apps.billing.models import Subscription
from apps.projects.models import Project
from apps.tenants.models import Membership, Organization

PASSWORD = "Qa-Seed-Password-1"


class Command(BaseCommand):
    """Create QA data for fuzzing and load tests (idempotent).

    Creates --tenants organizations `qa-org-<n>` on the Pro plan, each with
    an owner `qa-owner-<n>@example.com` (password Qa-Seed-Password-1) and
    --projects projects. Organization `qa-org-0` is the fuzzing target.
    """

    help = "Seed QA organizations, owners and projects."

    def add_arguments(self, parser):
        parser.add_argument("--tenants", type=int, default=1)
        parser.add_argument("--projects", type=int, default=3)

    @transaction.atomic
    def handle(self, *args, tenants, projects, **options):
        for n in range(tenants):
            org, _ = Organization.objects.get_or_create(slug=f"qa-org-{n}", defaults={"name": f"QA Org {n}"})
            Subscription.objects.update_or_create(organization=org, defaults={"plan": "pro"})
            owner = User.objects.filter(email=f"qa-owner-{n}@example.com").first()
            if owner is None:
                owner = User.objects.create_user(f"qa-owner-{n}@example.com", PASSWORD)
            Membership.objects.update_or_create(
                user=owner, organization=org, defaults={"role": Membership.Role.OWNER}
            )
            existing = Project.all_tenants.filter(organization=org).count()
            Project.all_tenants.bulk_create(
                Project(organization=org, name=f"QA project {i}", created_by=owner)
                for i in range(existing, projects)
            )
        self.stdout.write(f"Seeded {tenants} tenant(s) with {projects} project(s) each.")
