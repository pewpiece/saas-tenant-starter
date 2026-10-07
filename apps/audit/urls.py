from django.urls import path

from apps.audit.views import AuditLogListView

urlpatterns = [
    path("audit-log/", AuditLogListView.as_view(), name="audit-log"),
]
