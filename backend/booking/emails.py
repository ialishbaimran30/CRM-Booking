import logging
from urllib.parse import urlencode

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
        return False

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
        return True
    except Exception:
        logger.exception("Failed to send booking confirmation email for booking %s", booking.id)
        return False


def send_booking_rescheduled_email(booking, old_date, old_start_time, old_end_time):
    """Notify a client that their own booking was moved to a new date/time.

    Failures are logged, not raised, matching send_booking_confirmation_email.
    """
    client = booking.client
    if not client.email:
        return False

    context = {
        "client_name": client.full_name,
        "service_name": booking.service_name,
        "old_booking_date": old_date.strftime("%d %b %Y"),
        "old_start_time": old_start_time.strftime("%I:%M %p"),
        "old_end_time": old_end_time.strftime("%I:%M %p"),
        "booking_date": booking.booking_date.strftime("%d %b %Y"),
        "start_time": booking.start_time.strftime("%I:%M %p"),
        "end_time": booking.end_time.strftime("%I:%M %p"),
        "status": booking.get_status_display(),
    }

    subject = "Appointment Successfully Rescheduled"
    text_body = render_to_string("emails/booking_rescheduled.txt", context)
    html_body = render_to_string("emails/booking_rescheduled.html", context)

    try:
        email = EmailMultiAlternatives(
            subject=subject, body=text_body, from_email=settings.DEFAULT_FROM_EMAIL, to=[client.email],
        )
        email.attach_alternative(html_body, "text/html")
        email.send(fail_silently=False)
        return True
    except Exception:
        logger.exception("Failed to send reschedule email for booking %s", booking.id)
        return False


def send_booking_cancelled_email(booking, deleted=False):
    """Notify a client that their own booking was cancelled (or removed outright).

    Failures are logged, not raised, matching send_booking_confirmation_email.
    """
    client = booking.client
    if not client.email:
        return False

    context = {
        "client_name": client.full_name,
        "service_name": booking.service_name,
        "booking_date": booking.booking_date.strftime("%d %b %Y"),
        "start_time": booking.start_time.strftime("%I:%M %p"),
        "end_time": booking.end_time.strftime("%I:%M %p"),
        "deleted": deleted,
    }

    subject = "Booking Cancelled" if not deleted else "Booking Removed"
    text_body = render_to_string("emails/booking_cancelled.txt", context)
    html_body = render_to_string("emails/booking_cancelled.html", context)

    try:
        email = EmailMultiAlternatives(
            subject=subject, body=text_body, from_email=settings.DEFAULT_FROM_EMAIL, to=[client.email],
        )
        email.attach_alternative(html_body, "text/html")
        email.send(fail_silently=False)
        return True
    except Exception:
        logger.exception("Failed to send cancellation email for booking %s", booking.id)
        return False


def send_booking_updated_email(booking):
    """Notify a client that details of their own booking changed (not a
    reschedule or cancellation — e.g. price, service name, payment status).

    Failures are logged, not raised, matching send_booking_confirmation_email.
    """
    client = booking.client
    if not client.email:
        return False

    context = {
        "client_name": client.full_name,
        "service_name": booking.service_name,
        "booking_date": booking.booking_date.strftime("%d %b %Y"),
        "start_time": booking.start_time.strftime("%I:%M %p"),
        "end_time": booking.end_time.strftime("%I:%M %p"),
        "status": booking.get_status_display(),
        "price": booking.price,
    }

    subject = f"Your Booking Has Been Updated — {booking.service_name}"
    text_body = render_to_string("emails/booking_updated.txt", context)
    html_body = render_to_string("emails/booking_updated.html", context)

    try:
        email = EmailMultiAlternatives(
            subject=subject, body=text_body, from_email=settings.DEFAULT_FROM_EMAIL, to=[client.email],
        )
        email.attach_alternative(html_body, "text/html")
        email.send(fail_silently=False)
        return True
    except Exception:
        logger.exception("Failed to send booking-updated email for booking %s", booking.id)
        return False


def _slot_booking_link(booking_date, start_time, end_time):
    """Deep link into the Client Portal with the freed slot preselected."""
    params = urlencode({
        "date": booking_date.isoformat(),
        "start_time": start_time.strftime("%H:%M"),
        "end_time": end_time.strftime("%H:%M"),
    })
    return f"{settings.FRONTEND_BASE_URL}/client-portal/bookings?{params}"


def send_waitlist_slot_available_email(waitlist_entry):
    """Notify one waitlisted client that their requested slot is free again.

    Failures are logged, not raised, matching send_booking_confirmation_email.
    """
    client = waitlist_entry.client
    if not client.email:
        return False

    context = {
        "client_name": client.full_name,
        "booking_date": waitlist_entry.booking_date.strftime("%d %b %Y"),
        "start_time": waitlist_entry.start_time.strftime("%I:%M %p"),
        "end_time": waitlist_entry.end_time.strftime("%I:%M %p"),
        "book_now_url": _slot_booking_link(
            waitlist_entry.booking_date, waitlist_entry.start_time, waitlist_entry.end_time
        ),
    }

    subject = "Your Requested Appointment Slot is Now Available"
    text_body = render_to_string("emails/waitlist_slot_available.txt", context)
    html_body = render_to_string("emails/waitlist_slot_available.html", context)

    try:
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[client.email],
        )
        email.attach_alternative(html_body, "text/html")
        email.send(fail_silently=False)
        return True
    except Exception:
        logger.exception(
            "Failed to send waitlist availability email for waitlist entry %s", waitlist_entry.id
        )
        return False


def notify_waitlist_for_freed_slot(booking_date, start_time, end_time):
    """Email every client waiting on this exact slot that it's free again.

    Returns the number of emails successfully sent.
    """
    from .models import Waitlist

    entries = Waitlist.objects.filter(
        booking_date=booking_date, start_time=start_time, end_time=end_time
    ).select_related("client")

    sent = 0
    notified_ids = []
    for entry in entries:
        if send_waitlist_slot_available_email(entry):
            sent += 1
            notified_ids.append(entry.id)

    if notified_ids:
        from django.utils import timezone
        Waitlist.objects.filter(id__in=notified_ids).update(notified_at=timezone.now())

    return sent