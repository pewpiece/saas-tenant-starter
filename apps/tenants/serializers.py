from rest_framework import serializers

from apps.tenants.models import Invitation, Membership


class InvitationSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)
    invited_by = serializers.EmailField(source="invited_by.email", read_only=True, default=None)

    class Meta:
        model = Invitation
        fields = [
            "id",
            "email",
            "role",
            "status",
            "invited_by",
            "created_at",
            "expires_at",
            "accepted_at",
        ]
        read_only_fields = ["id", "status", "invited_by", "created_at", "expires_at", "accepted_at"]

    def get_unique_together_constraints(self, model):
        # DRF would build a validator from the conditional unique constraint
        # via model._default_manager.filter(...), which raises outside a
        # tenant (e.g. during schema generation). validate_email() performs
        # the same check, and the database constraint backs it up.
        return iter(())

    def validate_email(self, value):
        value = value.lower()
        # Django's EmailValidator does not enforce RFC 5321's 64-octet limit
        # on the local part; such an address can never receive the email.
        if len(value.rsplit("@", 1)[0].encode()) > 64:
            raise serializers.ValidationError("The part before @ can be at most 64 characters.")
        org = self.context["request"].tenant
        if Membership.objects.filter(organization=org, user__email__iexact=value).exists():
            raise serializers.ValidationError("This person is already a member.")
        if Invitation.objects.pending().filter(email=value).exists():
            raise serializers.ValidationError("This email already has a pending invitation.")
        return value


class AcceptInvitationSerializer(serializers.Serializer):
    token = serializers.CharField()
    # Only for invitees without an account; existing users authenticate instead.
    password = serializers.CharField(required=False, write_only=True, style={"input_type": "password"})
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)


class AcceptInvitationResponseSerializer(serializers.Serializer):
    organization = serializers.DictField()
    role = serializers.CharField()


class MemberUserSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    email = serializers.EmailField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)


class MemberSerializer(serializers.ModelSerializer):
    user = MemberUserSerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "user", "role", "created_at"]
        read_only_fields = ["id", "user", "created_at"]
