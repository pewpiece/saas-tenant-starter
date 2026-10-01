import pytest

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_user_has_no_username_field():
    assert not hasattr(User, "username")
    assert User.USERNAME_FIELD == "email"


def test_create_user_requires_email():
    with pytest.raises(ValueError):
        User.objects.create_user(email="", password="pw")


def test_create_user_normalizes_and_logs_in_with_email():
    user = User.objects.create_user(email="Person@Example.com", password="pw")
    assert user.email == "Person@example.com"
    assert user.check_password("pw")
