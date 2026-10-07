from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.tenants.api import AcceptInvitationView, InvitationViewSet

router = SimpleRouter()
router.register("invitations", InvitationViewSet, basename="invitation")

urlpatterns = [
    # Before the router, so "accept" is never read as an invitation id.
    path("invitations/accept/", AcceptInvitationView.as_view(), name="invitation-accept"),
    *router.urls,
]
