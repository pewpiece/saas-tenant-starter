from rest_framework import serializers

from apps.billing.plans import Plan


class PlanLimitsSerializer(serializers.Serializer):
    max_members = serializers.IntegerField(allow_null=True)
    max_projects = serializers.IntegerField(allow_null=True)
    features = serializers.ListField(child=serializers.CharField())


class UsageSerializer(serializers.Serializer):
    members = serializers.IntegerField()
    pending_invitations = serializers.IntegerField()
    projects = serializers.IntegerField()


class OverLimitSerializer(serializers.Serializer):
    members = serializers.BooleanField()
    projects = serializers.BooleanField()


class SubscriptionSerializer(serializers.Serializer):
    plan = serializers.ChoiceField(choices=Plan.choices)
    limits = PlanLimitsSerializer(read_only=True)
    usage = UsageSerializer(read_only=True)
    over_limit = OverLimitSerializer(read_only=True)
    warnings = serializers.ListField(child=serializers.CharField(), read_only=True)


class ChangePlanSerializer(serializers.Serializer):
    plan = serializers.ChoiceField(choices=Plan.choices)
