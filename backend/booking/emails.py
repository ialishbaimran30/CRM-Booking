import logging
from datetime import datetime, timezone as dt_timezone
from email.utils import parseaddr
from urllib.parse import urlencode

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)


def _ics_escape(value):
    """Escape a value for an iCalendar TEXT field (RFC 5545 §3.3.11)."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold_ics_line(line):
    """RFC 5545 §3.1: content lines longer than 75 octets are folded with
    CRLF followed by a single space, without splitting a multi-byte char."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    pieces = []
    while len(raw) > 75:
        cut = 75
        while cut > 0 and (raw[cut] & 0xC0) == 0x80:  # don't split a UTF-8 sequence
            cut -= 1
        pieces.append(raw[:cut].decode("utf-8"))
        raw = b" " + raw[cut:]
    pieces.append(raw.decode("utf-8"))
    return "\r\n".join(pieces)


def build_booking_calendar_invite(booking):
    """Return a METHOD:REQUEST iCalendar object for this booking so the
    confirmation email renders as a meeting invitation (Yes / No / Maybe) in
    Gmail and adds the event to the client's calendar on accept.

    This is independent of the Google Calendar API sync in
    booking/google_calendar.py: that path emails its own invite from the
    connected Google account only when Calendar is connected, whereas this
    one always travels with the confirmation email over the normal SMTP
    backend. Booking times are wall-clock in settings.TIME_ZONE (same as
    google_calendar._event_payload), converted here to UTC.
    """
    client = booking.client
    tz = timezone.get_default_timezone()

    def _utc(t):
        return timezone.make_aware(
            datetime.combine(booking.booking_date, t), tz
        ).astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    organizer_name, organizer_email = parseaddr(settings.DEFAULT_FROM_EMAIL)
    organizer_name = organizer_name or "CRM & Booking"
    domain = (organizer_email.split("@")[-1] if "@" in organizer_email else "") or "crm-booking"

    description = (
        f"Service: {booking.service_name}\n"
        f"Client: {client.full_name} ({client.email})\n"
        f"Booking ID: {booking.id}"
    )

    lines = [
        "BEGIN:VCALENDAR",
        "PRODID:-//CRM & Booking//Booking Confirmation//EN",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "METHOD:REQUEST",
        "BEGIN:VEVENT",
        f"UID:booking-{booking.pk}@{domain}",
        f"DTSTAMP:{datetime.now(dt_timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART:{_utc(booking.start_time)}",
        f"DTEND:{_utc(booking.end_time)}",
        f"SUMMARY:{_ics_escape(booking.service_name)} - {_ics_escape(client.full_name)}",
        f"DESCRIPTION:{_ics_escape(description)}",
        f"ORGANIZER;CN={_ics_escape(organizer_name)}:mailto:{organizer_email}",
        (
            f"ATTENDEE;CN={_ics_escape(client.full_name)};ROLE=REQ-PARTICIPANT;"
            f"PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{client.email}"
        ),
        "STATUS:CONFIRMED",
        "SEQUENCE:0",
        "TRANSP:OPAQUE",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(_fold_ics_line(line) for line in lines) + "\r\n"


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

        # Attach the meeting invite so Gmail shows the Yes / No / Maybe
        # buttons and the client can add it to their own calendar. Built
        # in a nested try so an invite-generation problem can never stop
        # the confirmation email itself from going out.
        try:
            ics = build_booking_calendar_invite(booking)
            # multipart/alternative part -> Gmail's inline RSVP widget.
            email.attach_alternative(ics, 'text/calendar; method=REQUEST; charset="UTF-8"')
            # file part -> Outlook / Apple Mail / download.
            email.attach("invite.ics", ics, 'text/calendar; method=REQUEST')
        except Exception:
            logger.exception(
                "Failed to build calendar invite for booking %s; "
                "sending confirmation without it", booking.id
            )

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