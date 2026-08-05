from django.db import models
from django.conf import settings
from booking.models import Booking


class Staff(models.Model):
    """Represents a staff member who can be assigned to bookings."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staff_profile"
    )
    title = models.CharField(max_length=150, blank=True)
    bio = models.TextField(blank=True)
    is_active_staff = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class Resource(models.Model):
    """Represents a physical or digital resource (Room, Equipment) that can be booked."""

    class ResourceType(models.TextChoices):
        ROOM = "ROOM", "Room"
        EQUIPMENT = "EQUIPMENT", "Equipment"
        OTHER = "OTHER", "Other"

    name = models.CharField(max_length=255)
    resource_type = models.CharField(
        max_length=50, choices=ResourceType.choices, default=ResourceType.ROOM
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.get_resource_type_display()})"


class BookingAssignment(models.Model):
    """Links bookings to staff and resources with conflict prevention."""

    booking = models.ForeignKey(
        Booking, on_delete=models.CASCADE, related_name="assignments"
    )
    staff = models.ForeignKey(
        Staff, on_delete=models.SET_NULL, null=True, blank=True, related_name="assignments"
    )
    resource = models.ForeignKey(
        Resource, on_delete=models.SET_NULL, null=True, blank=True, related_name="assignments"
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        staff_name = self.staff.user.username if self.staff else "No Staff"
        res_name = self.resource.name if self.resource else "No Resource"
        return f"Booking #{self.booking.id} -> Staff: {staff_name}, Resource: {res_name}"