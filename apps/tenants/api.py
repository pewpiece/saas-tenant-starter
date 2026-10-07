from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.invitations import accept_invitation, revoke_invitation, send_invitation
from apps.tenants.models import Invitation, Membership
from apps.tenants.permissions import IsTenantAdmin, has_role
from apps.tenants.serializers import (
    AcceptInvitationResponseSerializer,
    AcceptInvitationSerializer,
    InvitationSerializer,
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
        role = serializer.validated_data["role"]
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
