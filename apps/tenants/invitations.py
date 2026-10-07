from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotAuthenticated, PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.audit.services import record
from apps.billing.services import ensure_can_add_member, lock_organization
from apps.tenants.context import tenant_context
from apps.tenants.models import Invitation, Membership

INVALID_TOKEN = "This invitation is invalid, expired or has already been used."


def send_invitation(*, email, role, invited_by, org):
    """Create an invitation in the active tenant and email the link (after commit)."""
    lock_organization(org)
    ensure_can_add_member(org, count_pending_invitations=True)
    # The unique constraint allows one open invitation per email; an expired
    # one would block a fresh invite, so close it first.
    Invitation.objects.filter(
        email=email, accepted_at__isnull=True, revoked_at__isnull=True, expires_at__lte=timezone.now()
    ).update(revoked_at=timezone.now())
    invitation, raw_token = Invitation.issue(email=email, role=role, invited_by=invited_by)
    record(
        "invitation.create",
        actor=invited_by,
        target=invitation,
        changes={"email": email, "role": role},
    )
    link = settings.INVITATION_ACCEPT_URL.format(token=raw_token)
    transaction.on_commit(
        lambda: send_mail(
            subject=f"You're invited to join {org.name}",
            message=(
                f"{invited_by.email} invited you to join {org.name} as {role}.\n\n"
                f"Accept the invitation: {link}\n\n"
                f"This link works once and expires on {invitation.expires_at:%Y-%m-%d %H:%M} UTC."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
        )
    )
    return invitation


def accept_invitation(*, raw_token, request_user, password=None, first_name="", last_name=""):
    """Accept an invitation; return the new Membership.

    - Authenticated callers must be the invited email address.
    - Anonymous callers create an account (password required), unless an
      account for that email already exists: then they must authenticate.
    The organization always comes from the invitation, never the request.
    """
    invitation = (
        Invitation.all_tenants.select_for_update()
        .select_related("organization")
        .filter(token_hash=Invitation.hash_token(raw_token))
        .first()
    )
    if invitation is None or invitation.status != Invitation.Status.PENDING:
        raise ValidationError({"token": INVALID_TOKEN})

    org = invitation.organization
    with tenant_context(org):
        if request_user.is_authenticated:
            if request_user.email.lower() != invitation.email:
                raise PermissionDenied("This invitation was sent to a different email address.")
            user = request_user
        else:
            if User.objects.filter(email__iexact=invitation.email).exists():
                raise NotAuthenticated(
                    "An account with this email already exists. Authenticate to accept."
                )
            user = _create_invited_user(invitation.email, password, first_name, last_name)

        if Membership.objects.filter(user=user, organization=org).exists():
            raise ValidationError({"token": "You are already a member of this organization."})

        lock_organization(org)
        ensure_can_add_member(org, count_pending_invitations=False)
        membership = Membership.objects.create(user=user, organization=org, role=invitation.role)
        invitation.accepted_at = timezone.now()
        invitation.accepted_by = user
        invitation.save(update_fields=["accepted_at", "accepted_by"])
        record(
            "invitation.accept",
            actor=user,
            target=invitation,
            changes={"email": invitation.email, "role": invitation.role},
        )
    return membership


def _create_invited_user(email, password, first_name, last_name):
    if not password:
        raise ValidationError({"password": "A password is required to create your account."})
    candidate = User(email=email, first_name=first_name, last_name=last_name)
    try:
        validate_password(password, user=candidate)
    except DjangoValidationError as exc:
        raise ValidationError({"password": list(exc.messages)}) from exc
    return User.objects.create_user(
        email=email, password=password, first_name=first_name, last_name=last_name
    )


def revoke_invitation(invitation, *, actor):
    if invitation.status == Invitation.Status.ACCEPTED:
        raise ValidationError({"detail": "An accepted invitation cannot be revoked."})
    if invitation.revoked_at is None:
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=["revoked_at"])
        record("invitation.revoke", actor=actor, target=invitation, changes={"email": invitation.email})
