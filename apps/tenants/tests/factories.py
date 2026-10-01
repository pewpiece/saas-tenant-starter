import factory

from apps.tenants.models import Membership, Organization


class OrganizationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Organization

    name = factory.Sequence(lambda n: f"Org {n}")
    slug = factory.Sequence(lambda n: f"org-{n}")


class MembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Membership

    user = factory.SubFactory("apps.accounts.tests.factories.UserFactory")
    organization = factory.SubFactory(OrganizationFactory)
    role = Membership.Role.MEMBER
