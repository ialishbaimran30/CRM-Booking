from django.core.mail import send_mail
from django.conf import settings
from .models import Notification


class CommunicationService:
    """Service layer to manage emails, mock SMS, and in-app notifications."""

    @staticmethod
    def send_in_app_notification(user, title, message, notification_type,
                                  actor=None, booking=None, previous_value="", new_value=""):
        """Creates an in-app notification record — the single source of truth —
        and pushes it over WebSocket in real time. The extra kwargs are all
        optional/additive so every existing call site keeps working unchanged."""
        notification = Notification.objects.create(
            recipient=user,
            title=title,
            message=message,
            notification_type=notification_type,
            actor=actor,
            booking=booking,
            previous_value=previous_value,
            new_value=new_value,
        )
        CommunicationService._broadcast(notification)
        return notification

    @staticmethod
    def _upsert_cancelled_notification(user, title, message, notification_type,
                                        actor, booking, previous_value, new_value):
        """Cancellation updates the booking's existing Activity History entry
        for this recipient in place, instead of appending a new one — unlike
        every other lifecycle action (created/updated/rescheduled), which
        always adds a fresh row and is unaffected by this method."""
        from django.utils import timezone

        existing = Notification.objects.filter(recipient=user, booking=booking).order_by("-created_at").first()
        if existing is None:
            return CommunicationService.send_in_app_notification(
                user, title, message, notification_type,
                actor=actor, booking=booking, previous_value=previous_value, new_value=new_value,
            )
        existing.title = title
        existing.message = message
        existing.notification_type = notification_type
        existing.actor = actor
        existing.previous_value = previous_value
        existing.new_value = new_value
        existing.is_read = False
        existing.created_at = timezone.now()
        existing.save()
        CommunicationService._broadcast(existing)
        return existing

    @staticmethod
    def _broadcast(notification):
        """Deliver the just-created notification over the recipient's
        WebSocket group in real time. This is purely a delivery mechanism on
        top of the single DB write above — never a second creation path, and
        never allowed to raise (a broadcast failure must not break the
        booking action that triggered it)."""
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer
            from .serializers import NotificationSerializer

            layer = get_channel_layer()
            if layer is None:
                return
            async_to_sync(layer.group_send)(
                f"user_{notification.recipient_id}",
                {"type": "notification.message", "notification": NotificationSerializer(notification).data},
            )
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Failed to broadcast notification %s over WebSocket", notification.id
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

    @classmethod
    def _actor_role_label(cls, actor):
        if not actor:
            return "System"
        from accounts.permissions import get_user_role
        return get_user_role(actor) or "Client"

    @classmethod
    def notify_booking_event(cls, booking, *, actor, action, previous_value="", new_value=""):
        """Fan out ONE logical booking-lifecycle event to every relevant
        recipient (Client, Booking Managers, Admin) as an in-app notification
        (persisted here, then delivered live over WebSocket by
        send_in_app_notification/_broadcast above). This is purely additive
        to the existing email notifications in booking/emails.py — it does
        not touch, duplicate, or replace them.

        Recipient rule:
          - Admin: always included, so the Notification History stays
            complete even for actions Admin performs itself.
          - Every Booking Manager except the one who is the actor.
          - The booking's own Client, except when the Client is the actor
            (no need to notify someone of their own action).
        Each recipient gets exactly one Notification row for this event —
        this is the normal one-event-to-many-inboxes fan-out, not a duplicate.
        """
        from accounts.models import TeamRoleAssignment
        from django.contrib.auth import get_user_model

        User = get_user_model()
        actor_id = getattr(actor, "id", None)
        recipients = {}

        admin_assignment = TeamRoleAssignment.objects.filter(
            role_name="Admin"
        ).select_related("assigned_user").first()
        if admin_assignment and admin_assignment.assigned_user:
            recipients[admin_assignment.assigned_user_id] = admin_assignment.assigned_user

        for bm in TeamRoleAssignment.objects.filter(
            role_name="Booking Manager"
        ).select_related("assigned_user"):
            if bm.assigned_user and bm.assigned_user_id != actor_id:
                recipients[bm.assigned_user_id] = bm.assigned_user

        client_user = User.objects.filter(email__iexact=booking.client.email).first()
        if client_user and client_user.id != actor_id:
            recipients[client_user.id] = client_user

        if not recipients:
            return []

        action_meta = {
            "created": ("Booking Created", Notification.NotificationType.BOOKING_CREATED),
            "updated": ("Booking Updated", Notification.NotificationType.BOOKING_UPDATED),
            "rescheduled": ("Booking Rescheduled", Notification.NotificationType.BOOKING_RESCHEDULED),
            "cancelled": ("Booking Cancelled", Notification.NotificationType.BOOKING_CANCELLATION),
        }
        title, notif_type = action_meta[action]
        actor_label = cls._actor_role_label(actor)
        message = (
            f"{title} — {booking.client.full_name} ({booking.service_name}) "
            f"on {booking.booking_date.strftime('%d %b %Y')}. By {actor_label}."
        )

        created = []
        for user in recipients.values():
            if action == "cancelled":
                created.append(cls._upsert_cancelled_notification(
                    user, title, message, notif_type, actor, booking, previous_value, new_value,
                ))
            else:
                created.append(cls.send_in_app_notification(
                    user, title, message, notif_type,
                    actor=actor, booking=booking,
                    previous_value=previous_value, new_value=new_value,
                ))
        return created

    @classmethod
    def notify_waitlist_slot_available(cls, waitlist_entry):
        """In-app companion to send_waitlist_slot_available_email (booking/emails.py)
        — purely additive, does not touch the email flow at all."""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        client_user = User.objects.filter(email__iexact=waitlist_entry.client.email).first()
        if not client_user:
            return None
        title = "Slot Available"
        message = (
            f"A slot you were waiting for on {waitlist_entry.booking_date.strftime('%d %b %Y')} "
            f"at {waitlist_entry.start_time.strftime('%I:%M %p')} is now available."
        )
        return cls.send_in_app_notification(
            client_user, title, message, Notification.NotificationType.WAITLIST_SLOT_AVAILABLE
        )