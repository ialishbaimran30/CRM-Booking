from django.db import models
from django.conf import settings


class Notification(models.Model):
    """Represents an in-app notification / communication log."""

    class NotificationType(models.TextChoices):
        BOOKING_CONFIRMATION = "BOOKING_CONFIRMATION", "Booking Confirmation"
        BOOKING_CANCELLATION = "BOOKING_CANCELLATION", "Booking Cancellation"
        REMINDER = "REMINDER", "Reminder"
        GENERAL = "GENERAL", "General"
        # Additive — used by the booking-lifecycle notification hooks
        # (notifications/services.py: notify_booking_event). Existing choices
        # above are unchanged.
        BOOKING_CREATED = "BOOKING_CREATED", "Booking Created"
        BOOKING_UPDATED = "BOOKING_UPDATED", "Booking Updated"
        BOOKING_RESCHEDULED = "BOOKING_RESCHEDULED", "Booking Rescheduled"
        WAITLIST_SLOT_AVAILABLE = "WAITLIST_SLOT_AVAILABLE", "Waitlist Slot Available"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(
        max_length=50, choices=NotificationType.choices, default=NotificationType.GENERAL
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # Additive fields for the Admin Notification History (who/what/which/when).
    # All nullable/blank so every existing Notification row and every existing
    # call to send_in_app_notification() keeps working unchanged.
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="actioned_notifications",
        help_text="The authenticated user who actually performed the action.",
    )
    booking = models.ForeignKey(
        "booking.Booking", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="notifications",
    )
    previous_value = models.CharField(max_length=255, blank=True)
    new_value = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"Notification for {self.recipient.username} - {self.title}"