from django.contrib.auth import authenticate
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import AuthToken
from apps.accounts.serializers import (
    MeSerializer,
    SignupResponseSerializer,
    SignupSerializer,
    TokenRequestSerializer,
    TokenResponseSerializer,
)
from apps.core.authentication import (
    BearerTokenAuthentication,
    ensure_not_locked_out,
    record_auth_failure,
)


class SignupView(generics.GenericAPIView):
    """Create a user plus their first organization, with them as owner."""

    serializer_class = SignupSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "auth"

    @extend_schema(responses={201: SignupResponseSerializer})
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        org = result["organization"]
        return Response(
            {"user": MeSerializer(result["user"]).data, "organization": {"slug": org.slug, "name": org.name}},
            status=status.HTTP_201_CREATED,
        )


class MeView(generics.RetrieveAPIView):
    """The current user and every organization they belong to.

    Clients switch between organizations by sending a different X-Org
    header; this lists the valid values.
    """

    serializer_class = MeSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class TokenView(generics.GenericAPIView):
    """Exchange email + password for a bearer token (POST), or revoke the
    token being used (DELETE).

    Wrong passwords count toward the same per-IP lockout as HTTP Basic auth.
    """

    serializer_class = TokenRequestSerializer
    throttle_scope = "auth"

    def get_authenticators(self):
        # Only DELETE authenticates (with the token it revokes); POST is the login.
        if getattr(self.request, "method", None) == "DELETE":
            return [BearerTokenAuthentication()]
        return []

    def get_permissions(self):
        if getattr(self.request, "method", None) == "DELETE":
            return [IsAuthenticated()]
        return [AllowAny()]

    @extend_schema(responses={201: TokenResponseSerializer})
    def post(self, request):
        ensure_not_locked_out(request)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            record_auth_failure(request)
            return Response({"detail": "Invalid email or password."}, status=status.HTTP_401_UNAUTHORIZED)
        token, key = AuthToken.issue(user)
        return Response({"token": key, "expires_at": token.expires_at}, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={204: None})
    def delete(self, request):
        if not isinstance(request.auth, AuthToken):
            return Response(
                {"detail": "Authenticate with the bearer token you want to revoke."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        request.auth.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
