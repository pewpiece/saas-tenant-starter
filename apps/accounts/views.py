from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.accounts.serializers import MeSerializer, SignupResponseSerializer, SignupSerializer


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
