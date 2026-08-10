from rest_framework import serializers
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    # Additive, read-only fields for the Admin Notification History display —
    # existing fields above are unchanged.
    actor_name = serializers.CharField(source="actor.full_name", read_only=True, default=None)
    actor_role = serializers.SerializerMethodField()
    client_name = serializers.CharField(source="booking.client.full_name", read_only=True, default=None)
    booking_id = serializers.IntegerField(source="booking.id", read_only=True, default=None)

    class Meta:
        model = Notification
        fields = [
            "id", "recipient", "title", "message", "notification_type", "is_read", "created_at",
            "actor", "actor_name", "actor_role", "booking", "booking_id", "client_name",
            "previous_value", "new_value",
        ]
        read_only_fields = ["recipient", "created_at", "actor", "booking"]

    def get_actor_role(self, obj):
        if not obj.actor_id:
            return None
        from accounts.permissions import get_user_role
        return get_user_role(obj.actor) or "Client"