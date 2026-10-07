from django.conf import settings
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from apps.tenants.exceptions import LastOwnerError
from apps.tenants.models import Membership


def ensure_not_sole_owner(user):
    """Raise LastOwnerError if deleting `user` would leave an org ownerless.

    The user's memberships are removed by cascade (which bypasses
    Membership.delete()), so this has to be checked on the user. Transfer
    ownership or delete the organization first.
    """
    owned = Membership.objects.filter(user=user, role=Membership.Role.OWNER)
    for membership in owned.select_related("organization"):
        if membership._is_last_owner():
            raise LastOwnerError(
                f"{user} is the only owner of {membership.organization}; "
                "transfer ownership or delete the organization first."
            )


@receiver(pre_delete, sender=settings.AUTH_USER_MODEL)
def prevent_orphaned_organizations(sender, instance, **kwargs):
    # Backstop for queryset/admin bulk deletes. User.delete() runs the same
    # check before Django opens its deletion transaction, so the common path
    # fails cleanly without breaking the caller's transaction.
    ensure_not_sole_owner(instance)
