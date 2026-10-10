from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils.text import slugify
from rest_framework import serializers

from apps.accounts.models import User
from apps.tenants.models import Membership, Organization


class SignupSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    organization_name = serializers.CharField(max_length=255)
    organization_slug = serializers.SlugField(max_length=50, required=False)

    def validate_email(self, value):
        value = User.objects.normalize_email(value)
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate(self, attrs):
        slug = attrs.get("organization_slug") or slugify(attrs["organization_name"])[:50]
        if not slug:
            raise serializers.ValidationError(
                {"organization_slug": "Choose a slug (letters, numbers, hyphens)."}
            )
        if Organization.objects.filter(slug=slug).exists():
            raise serializers.ValidationError({"organization_slug": "This slug is taken."})
        attrs["organization_slug"] = slug

        candidate = User(
            email=attrs["email"],
            first_name=attrs.get("first_name", ""),
            last_name=attrs.get("last_name", ""),
        )
        try:
            validate_password(attrs["password"], user=candidate)
        except Exception as exc:  # django ValidationError -> DRF ValidationError
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        from apps.tenants.services import create_organization

        user = User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
        )
        org = create_organization(
            name=validated_data["organization_name"],
            slug=validated_data["organization_slug"],
            owner=user,
        )
        return {"user": user, "organization": org}


class MembershipSummarySerializer(serializers.ModelSerializer):
    slug = serializers.CharField(source="organization.slug")
    name = serializers.CharField(source="organization.name")

    class Meta:
        model = Membership
        fields = ["slug", "name", "role"]


class MeSerializer(serializers.ModelSerializer):
    organizations = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "organizations"]

    def get_organizations(self, user) -> list[dict]:
        memberships = user.memberships.select_related("organization").order_by("organization__slug")
        return MembershipSummarySerializer(memberships, many=True).data


class SignupResponseSerializer(serializers.Serializer):
    user = MeSerializer()


class TokenRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


class TokenResponseSerializer(serializers.Serializer):
    token = serializers.CharField(help_text="Send as `Authorization: Bearer <token>`.")
    expires_at = serializers.DateTimeField()
