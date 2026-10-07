from django.contrib import admin

from apps.projects.models import Project
from apps.tenants.admin import TenantOwnedAdmin


@admin.register(Project)
class ProjectAdmin(TenantOwnedAdmin):
    list_display = ("name", "organization", "created_by", "created_at")
    search_fields = ("name",)
    autocomplete_fields = ("created_by",)
