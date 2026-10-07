from dataclasses import dataclass

from django.db import models


class Plan(models.TextChoices):
    FREE = "free", "Free"
    PRO = "pro", "Pro"


PROJECT_EXPORT = "project_export"


@dataclass(frozen=True)
class PlanLimits:
    max_members: int | None  # None = unlimited
    max_projects: int | None
    features: frozenset


LIMITS = {
    Plan.FREE: PlanLimits(max_members=3, max_projects=5, features=frozenset()),
    Plan.PRO: PlanLimits(max_members=None, max_projects=None, features=frozenset({PROJECT_EXPORT})),
}
