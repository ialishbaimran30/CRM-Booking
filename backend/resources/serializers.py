from rest_framework import serializers
from .models import Staff, Resource, BookingAssignment
from .services import ResourceSchedulingService


class StaffSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Staff
        fields = ["id", "user", "username", "email", "title", "bio", "is_active_staff", "created_at"]
        read_only_fields = ["user"]


class ResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resource
        fields = ["id", "name", "resource_type", "description", "is_active", "created_at"]


class BookingAssignmentSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source="staff.user.username", read_only=True)
    resource_name = serializers.CharField(source="resource.name", read_only=True)

    class Meta:
        model = BookingAssignment
        fields = ["id", "booking", "staff", "staff_name", "resource", "resource_name", "assigned_at"]

    def validate(self, data):
        booking = data.get("booking")
        staff = data.get("staff")
        resource = data.get("resource")

        ResourceSchedulingService.validate_assignment_conflicts(
            booking=booking,
            staff=staff,
            resource=resource,
            start_time=booking.start_time,
            end_time=booking.end_time,
            booking_date=booking.booking_date
        )
        return data