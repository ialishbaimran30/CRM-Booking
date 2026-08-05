from django.db.models.signals import post_save
from django.dispatch import receiver

from .emails import send_booking_confirmation_email
from .models import Booking


@receiver(post_save, sender=Booking)
def send_confirmation_on_booking_created(sender, instance, created, **kwargs):
    """Every new booking automatically triggers a confirmation email to the client."""
    if created:
        send_booking_confirmation_email(instance)