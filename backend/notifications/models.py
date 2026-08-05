from django.db import models
from django.conf import settings


class Notification(models.Model):
    """Represents an in-app notification / communication log."""

    class NotificationType(models.TextChoices):
        BOOKING_CONFIRMATION = "BOOKING_CONFIRMATION", "Booking Confirmation"
        BOOKING_CANCELLATION = "BOOKING_CANCELLATION", "Booking Cancellation"
        REMINDER = "REMINDER", "Reminder"
        GENERAL = "GENERAL", "General"

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

    def __str__(self):
        return f"Notification for {self.recipient.username} - {self.title}"