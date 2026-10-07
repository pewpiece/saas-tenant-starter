from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record
from apps.tenants.exceptions import LastOwnerError
from apps.tenants.invitations import accept_invitation, revoke_invitation, send_invitation
from apps.tenants.models import Invitation, Membership
from apps.tenants.permissions import IsTenantAdmin, has_role
from apps.tenants.serializers import (
    AcceptInvitationResponseSerializer,
    AcceptInvitationSerializer,
    InvitationSerializer,
    MemberSerializer,
)
from apps.tenants.views import TenantScopedViewMixin


class InvitationViewSet(
    TenantScopedViewMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Invitations to the active organization (admins and owners).

    Only owners can invite someone as owner. DELETE revokes the invitation.
    """

    serializer_class = InvitationSerializer
    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def get_queryset(self):
        return self.tenant_queryset(
            lambda: Invitation.objects.select_related("invited_by"), Invitation.all_tenants.none()
        )

    def perform_create(self, serializer):
        # The model default is not copied into validated_data when the
        # client omits "role", so apply it here.
        role = serializer.validated_data.get("role", Membership.Role.MEMBER)
        if role == Membership.Role.OWNER and not has_role(self.request, Membership.Role.OWNER):
            raise PermissionDenied("Only an owner can invite another owner.")
        serializer.instance = send_invitation(
            email=serializer.validated_data["email"],
            role=role,
            invited_by=self.request.user,
            org=self.request.tenant,
        )

    def perform_destroy(self, instance):
        revoke_invitation(instance, actor=self.request.user)


class AcceptInvitationView(APIView):
    """Accept an invitation with the token from the email.

    New users send a password to create their account; existing users
    authenticate (Basic or session) and send only the token.
    """

    permission_classes = [AllowAny]
    throttle_scope = "auth"

    @extend_schema(request=AcceptInvitationSerializer, responses={200: AcceptInvitationResponseSerializer})
    def post(self, request):
        serializer = AcceptInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        membership = accept_invitation(
            raw_token=data["token"],
            request_user=request.user,
            password=data.get("password"),
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
        )
        org = membership.organization
        return Response(
            {"organization": {"slug": org.slug, "name": org.name}, "role": membership.role},
            status=status.HTTP_200_OK,
        )


class LastOwnerConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "An organization must keep at least one owner."
    default_code = "last_owner"


class MemberViewSet(
    TenantScopedViewMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Members of the active organization.

    - Everyone can list members.
    - Only owners change roles (PATCH {"role": ...}).
    - Owners remove anyone; admins remove plain members; anyone can leave
      (DELETE their own membership).
    - The last owner can be neither demoted nor removed (409).
    """

    serializer_class = MemberSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        # Membership is not a TenantOwnedModel, so scope it explicitly.
        return self.tenant_queryset(
            lambda: Membership.objects.filter(organization=self.request.tenant)
            .select_related("user")
            .order_by("created_at", "id"),
            Membership.objects.none(),
        )

    def perform_update(self, serializer):
        if not has_role(self.request, Membership.Role.OWNER):
            raise PermissionDenied("Only an owner can change roles.")
        old_role = serializer.instance.role
        try:
            membership = serializer.save()
        except LastOwnerError as exc:
            raise LastOwnerConflict() from exc
        if membership.role != old_role:
            record(
                "member.role_change",
                actor=self.request.user,
                target=membership,
                changes={"user": membership.user.email, "role": [old_role, membership.role]},
            )

    def perform_destroy(self, instance):
        is_self = instance.user_id == self.request.user.id
        allowed = (
            is_self
            or has_role(self.request, Membership.Role.OWNER)
            or (has_role(self.request, Membership.Role.ADMIN) and instance.role == Membership.Role.MEMBER)
        )
        if not allowed:
            raise PermissionDenied("You cannot remove this member.")
        # Recorded first because delete() clears the pk; if the delete is
        # refused, the request's transaction rolls the entry back too.
        record(
            "member.leave" if is_self else "member.remove",
            actor=self.request.user,
            target=instance,
            changes={"user": instance.user.email, "role": instance.role},
        )
        try:
            instance.delete()
        except LastOwnerError as exc:
            raise LastOwnerConflict() from exc
