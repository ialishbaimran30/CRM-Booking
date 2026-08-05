import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def send_booking_confirmation_email(booking):
    """Send a confirmation email to the client for a newly created booking.

    Failures are logged, not raised — a booking should still succeed even
    if the email provider is temporarily down.
    """
    client = booking.client
    if not client.email:
        return

    context = {
        "client_name": client.full_name,
        "service_name": booking.service_name,
        "booking_date": booking.booking_date.strftime("%d %b %Y"),
        "start_time": booking.start_time.strftime("%I:%M %p"),
        "end_time": booking.end_time.strftime("%I:%M %p"),
        "status": booking.get_status_display(),
        "price": booking.price,
    }

    subject = f"Booking Confirmed — {booking.service_name} on {context['booking_date']}"
    text_body = render_to_string("emails/booking_confirmation.txt", context)
    html_body = render_to_string("emails/booking_confirmation.html", context)

    try:
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[client.email],
        )
        email.attach_alternative(html_body, "text/html")
        email.send(fail_silently=False)
    except Exception:
        logger.exception("Failed to send booking confirmation email for booking %s", booking.id)