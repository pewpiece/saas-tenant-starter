from django.urls import path

from apps.billing.views import SubscriptionView

urlpatterns = [
    path("subscription/", SubscriptionView.as_view(), name="subscription"),
]
