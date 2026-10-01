import factory

from apps.accounts.models import User


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    first_name = "Test"
    last_name = "User"

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        self.set_password(extracted or "testpass123")
        if create:
            self.save()
