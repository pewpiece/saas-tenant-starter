from rest_framework import serializers

from apps.audit.models import AuditLogEntry


class AuditLogEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLogEntry
        fields = [
            "id",
            "action",
            "actor",
            "actor_email",
            "target_type",
            "target_id",
            "target_repr",
            "changes",
            "created_at",
        ]
        read_only_fields = fields
