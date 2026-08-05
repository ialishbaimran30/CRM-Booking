from django.core.mail import send_mail
from django.conf import settings
from .models import Notification


class CommunicationService:
    """Service layer to manage emails, mock SMS, and in-app notifications."""

    @staticmethod
    def send_in_app_notification(user, title, message, notification_type):
        """Creates an in-app notification record (ready for WebSockets)."""
        return Notification.objects.create(
            recipient=user,
            title=title,
            message=message,
            notification_type=notification_type
        )

    @staticmethod
    def send_email_notification(subject, message, recipient_email):
        """Sends an actual email using Django's configured backend."""
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient_email],
                fail_silently=False,
            )
        except Exception as e:
            print(f"Email sending failed: {e}")

    @staticmethod
    def send_mock_sms(phone_number, message):
        """Mock implementation for SMS dispatch."""
        print(f"[MOCK SMS] Sending to {phone_number}: {message}")
        return True

    @classmethod
    def trigger_booking_confirmation(cls, booking):
        """Triggers all notifications when a booking is confirmed."""
        user = booking.created_by
        client = booking.client
        
        title = "Booking Confirmed!"
        msg = f"Your booking for {booking.service_name} on {booking.booking_date} has been confirmed."

        # 1. In-app notification
        cls.send_in_app_notification(user, title, msg, Notification.NotificationType.BOOKING_CONFIRMATION)

        # 2. Email notification (if client has email)
        if client.email:
            cls.send_email_notification(title, msg, client.email)

        # 3. Mock SMS (if client has phone number)
        if client.phone_number:
            cls.send_mock_sms(client.phone_number, msg)

    @classmethod
    def trigger_booking_cancellation(cls, booking):
        """Triggers notifications when a booking is cancelled."""
        user = booking.created_by
        client = booking.client
        
        title = "Booking Cancelled"
        msg = f"Your booking for {booking.service_name} scheduled on {booking.booking_date} has been cancelled."

        cls.send_in_app_notification(user, title, msg, Notification.NotificationType.BOOKING_CANCELLATION)
        
        if client.email:
            cls.send_email_notification(title, msg, client.email)
        if client.phone_number:
            cls.send_mock_sms(client.phone_number, msg)