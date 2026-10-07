from django import forms
from django.contrib import admin

from apps.tenants.models import Membership, Organization


class TenantOwnedAdminForm(forms.ModelForm):
    """Lets staff pick the organization when creating a tenant-owned row.

    `organization` is editable=False on the model (so API serializers and
    forms can never set it), so the admin adds it as an explicit field. It is
    fixed once the row exists, matching the model's immutability rule.
    """

    organization = forms.ModelChoiceField(queryset=Organization.objects.all())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["organization"].initial = self.instance.organization_id
            self.fields["organization"].disabled = True

    def save(self, commit=True):
        if not self.instance.pk:
            self.instance.organization = self.cleaned_data["organization"]
        return super().save(commit)


class TenantOwnedAdmin(admin.ModelAdmin):
    """Base admin for TenantOwnedModel subclasses.

    The admin is a cross-tenant support tool, so it reads through the
    explicit `all_tenants` manager instead of the tenant-scoped default
    manager (which would raise with no active tenant).
    """

    form = TenantOwnedAdminForm
    list_filter = ("organization",)

    def get_queryset(self, request):
        queryset = self.model.all_tenants.get_queryset()
        ordering = self.get_ordering(request)
        if ordering:
            queryset = queryset.order_by(*ordering)
        return queryset

    def get_form(self, request, obj=None, **kwargs):
        # `organization` is declared on the form; it must not be passed to
        # modelform_factory, which rejects non-editable model fields.
        if kwargs.get("fields"):
            kwargs["fields"] = [f for f in kwargs["fields"] if f != "organization"]
        return super().get_form(request, obj, **kwargs)

    def get_fields(self, request, obj=None):
        fields = super().get_fields(request, obj)
        return ["organization", *[f for f in fields if f != "organization"]]


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    autocomplete_fields = ("user",)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "created_at")
    search_fields = ("slug", "name")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [MembershipInline]


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "created_at")
    list_filter = ("role",)
    search_fields = ("user__email", "organization__slug")
    autocomplete_fields = ("user", "organization")
