from django.urls import path

from apps.accounts.views import MeView, SignupView, TokenView

urlpatterns = [
    path("auth/signup/", SignupView.as_view(), name="signup"),
    path("auth/token/", TokenView.as_view(), name="token"),
    path("me/", MeView.as_view(), name="me"),
]
