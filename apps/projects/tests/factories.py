import factory

from apps.projects.models import Project


class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Project

    name = factory.Sequence(lambda n: f"Project {n}")
    description = ""
    organization = factory.SubFactory("apps.tenants.tests.factories.OrganizationFactory")
    created_by = factory.SubFactory("apps.accounts.tests.factories.UserFactory")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        # Test fixtures need to create projects across multiple orgs without
        # a request-scoped active tenant, so go through `all_tenants`
        # (the same escape hatch admin/system code uses) with an explicit
        # `organization` rather than the tenant-filtered default manager.
        return model_class.all_tenants.create(*args, **kwargs)
