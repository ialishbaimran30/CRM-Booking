"""The booking-confirmation email must carry a METHOD:REQUEST calendar
invite so Gmail renders the Yes / No / Maybe RSVP buttons and the client
can add the event to their own calendar.

Before the SMTP provider change the RSVP buttons came from the Google
Calendar API sync (sendUpdates=all in booking/google_calendar.py), which
only fires when Calendar is connected. This invite always travels with the
confirmation email over the normal SMTP backend and is independent of that
sync.
"""
from datetime import date, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings

from accounts.models import User
from clients.models import Client

from .emails import build_booking_calendar_invite
from .models import Booking, Service

FUTURE = date.today() + timedelta(days=10)


def _calendar_parts(message):
    return [
        (content, mime)
        for content, mime in message.alternatives
        if mime.startswith("text/calendar")
    ]


def _unfold(ics):
    """Reverse RFC 5545 line folding (CRLF + single space) for assertions."""
    return ics.replace("\r\n ", "").replace("\r\n", "\n")


@override_settings(
    TIME_ZONE="Asia/Karachi",
    DEFAULT_FROM_EMAIL="CRM & Booking <alishba.im13@gmail.com>",
)
class BookingConfirmationInviteTests(TestCase):
    def setUp(self):
        mail.outbox = []
        self.service = Service.objects.create(name="Consult", hourly_rate=Decimal("100.00"))
        self.user = User.objects.create_user(
            username="c1", email="c1@example.com", password="test-pass-12345", full_name="C One"
        )
        self.client_rec = Client.objects.create(full_name="Alice Client", email="alice@example.com")

    def _make_booking(self, start=time(14, 0), end=time(15, 0)):
        return Booking.objects.create(
            client=self.client_rec, service=self.service, service_name="Consult",
            booking_date=FUTURE, start_time=start, end_time=end,
            price=Decimal("100.00"), rate_snapshot=Decimal("100.00"),
            status=Booking.BookingStatus.PENDING, created_by=self.user,
        )

    def test_confirmation_email_still_has_plain_and_html_parts(self):
        self._make_booking()
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertTrue(msg.body.strip())  # text/plain
        html = [c for c, m in msg.alternatives if m == "text/html"]
        self.assertEqual(len(html), 1)
        self.assertEqual(msg.to, ["alice@example.com"])

    def test_confirmation_email_carries_a_method_request_calendar_part(self):
        self._make_booking()
        cal = _calendar_parts(mail.outbox[0])
        self.assertEqual(len(cal), 1, "exactly one text/calendar alternative expected")
        raw, mime = cal[0]
        self.assertIn("method=REQUEST", mime)
        self.assertIn("\r\n", raw)  # CRLF line endings per RFC 5545
        content = _unfold(raw)
        self.assertIn("BEGIN:VCALENDAR", content)
        self.assertIn("METHOD:REQUEST", content)
        self.assertIn("BEGIN:VEVENT", content)
        self.assertIn("SUMMARY:Consult - Alice Client", content)
        self.assertIn("ORGANIZER;CN=CRM & Booking:mailto:alishba.im13@gmail.com", content)
        self.assertIn("RSVP=TRUE:mailto:alice@example.com", content)
        self.assertIn("UID:booking-", content)

    def test_ics_file_is_attached_for_non_gmail_clients(self):
        self._make_booking()
        attachments = mail.outbox[0].attachments
        ics = [a for a in attachments if a[0] == "invite.ics"]
        self.assertEqual(len(ics), 1)
        self.assertIn("BEGIN:VEVENT", ics[0][1])
        self.assertIn("text/calendar", ics[0][2])

    def test_local_booking_time_is_converted_to_utc_in_the_invite(self):
        # 14:00-15:00 Asia/Karachi (UTC+5) -> 09:00-10:00 UTC
        self._make_booking(start=time(14, 0), end=time(15, 0))
        content = _calendar_parts(mail.outbox[0])[0][0]
        stamp = FUTURE.strftime("%Y%m%d")
        self.assertIn(f"DTSTART:{stamp}T090000Z", content)
        self.assertIn(f"DTEND:{stamp}T100000Z", content)

    def test_confirmation_email_still_sends_if_invite_build_fails(self):
        with patch(
            "booking.emails.build_booking_calendar_invite",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertLogs("booking.emails", level="ERROR"):
                booking = self._make_booking()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(_calendar_parts(mail.outbox[0]), [])
        self.assertTrue(getattr(booking, "_email_sent", False))

    def test_no_email_and_no_invite_when_client_has_no_address(self):
        self.client_rec.email = ""
        self.client_rec.save(update_fields=["email"])
        self._make_booking()
        self.assertEqual(len(mail.outbox), 0)

    def test_invite_builder_is_valid_without_touching_google_calendar(self):
        booking = self._make_booking()
        ics = build_booking_calendar_invite(booking)
        self.assertTrue(ics.startswith("BEGIN:VCALENDAR\r\n"))
        self.assertTrue(ics.strip().endswith("END:VCALENDAR"))
        self.assertEqual(booking.google_event_id, None)  # sync path untouched
