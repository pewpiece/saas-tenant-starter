from django.urls import path

from apps.accounts.views import MeView, SignupView

urlpatterns = [
    path("auth/signup/", SignupView.as_view(), name="signup"),
    path("me/", MeView.as_view(), name="me"),
]
