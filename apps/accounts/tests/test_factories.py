"""D-10: the test suite itself must run clean (no factory_boy deprecation noise)."""

import warnings

import pytest

from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory

pytestmark = pytest.mark.django_db


def test_user_factory_emits_no_deprecation_warning():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        user = UserFactory()

    assert [w for w in caught if issubclass(w.category, DeprecationWarning)] == []
    user.refresh_from_db()
    assert user.check_password(DEFAULT_PASSWORD)
