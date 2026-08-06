from django.db.models.signals import post_save
from django.dispatch import receiver

from .emails import send_booking_confirmation_email
from .models import Booking


@receiver(post_save, sender=Booking)
def send_confirmation_on_booking_created(sender, instance, created, **kwargs):
    """Every new booking automatically triggers a confirmation email to the client."""
    if created:
        # Stashed on the instance (not persisted) so the response can report
        # whether the email actually went out.
        instance._email_sent = send_booking_confirmation_email(instance)