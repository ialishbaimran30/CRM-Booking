"""Google Calendar sync for bookings.

Every public method returns (ok, event_id, error) and never raises — a
Calendar failure must never fail a booking (booking/views.py callers treat
any ok=False the same way: log it, mark the booking's sync status, move on).
"""
import logging

import requests
from django.conf import settings
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials

from .crypto import decrypt_token
from .models import GoogleCalendarCredential

logger = logging.getLogger(__name__)

CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"


def _get_access_token():
    """Return (access_token, calendar_id, error). Loads the singleton
    credential row and refreshes its access token via the stored refresh
    token — never raises."""
    credential = GoogleCalendarCredential.objects.first()
    if credential is None:
        return None, None, "Google Calendar is not connected."

    refresh_token = decrypt_token(credential.refresh_token_encrypted)
    if not refresh_token:
        return None, None, "Stored Google Calendar credential could not be decrypted."

    try:
        creds = Credentials(
            None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CALENDAR_CLIENT_ID,
            client_secret=settings.GOOGLE_CALENDAR_CLIENT_SECRET,
            scopes=[CALENDAR_SCOPE],
        )
        creds.refresh(GoogleAuthRequest())
        return creds.token, credential.calendar_id, None
    except Exception as exc:
        logger.exception("Failed to refresh Google Calendar access token")
        return None, None, str(exc)


def _event_payload(booking):
    client = booking.client
    start_dt = f"{booking.booking_date.isoformat()}T{booking.start_time.strftime('%H:%M:%S')}"
    end_dt = f"{booking.booking_date.isoformat()}T{booking.end_time.strftime('%H:%M:%S')}"
    description = (
        f"Service: {booking.service_name}\n"
        f"Date: {booking.booking_date.isoformat()}\n"
        f"Time: {booking.start_time.strftime('%H:%M')} - {booking.end_time.strftime('%H:%M')}\n"
        f"Client: {client.full_name} ({client.email})\n"
        f"Booking ID: {booking.id}\n"
        f"Status: {booking.get_status_display()}"
    )
    payload = {
        "summary": f"{booking.service_name} - {client.full_name}",
        "description": description,
        "start": {"dateTime": start_dt, "timeZone": settings.TIME_ZONE},
        "end": {"dateTime": end_dt, "timeZone": settings.TIME_ZONE},
    }
    if client.email:
        payload["attendees"] = [{"email": client.email}]
    return payload


def _confirm_attendee(booking, event_data):
    """An HTTP 200 from Google only proves the event itself was written —
    it does NOT prove the client was actually added/invited (Google can
    silently drop an attendee, e.g. workspace external-guest restrictions
    or a malformed entry, while still returning 200). The API always
    echoes the persisted event back, so cross-check the attendee is
    actually present before trusting the invite went out."""
    client_email = (booking.client.email or "").strip().lower()
    if not client_email:
        return True
    returned_emails = {
        (a.get("email") or "").strip().lower() for a in event_data.get("attendees", [])
    }
    return client_email in returned_emails


class GoogleCalendarService:
    """Backend-only Calendar sync. Tokens/API calls never reach the frontend."""

    @staticmethod
    def create_event(booking):
        access_token, calendar_id, error = _get_access_token()
        if error:
            return False, None, error
        try:
            resp = requests.post(
                f"{CALENDAR_API_BASE}/calendars/{calendar_id}/events",
                params={"sendUpdates": "all"},
                headers={"Authorization": f"Bearer {access_token}"},
                json=_event_payload(booking),
                timeout=10,
            )
            resp.raise_for_status()
            event_data = resp.json()
            event_id = event_data.get("id")
            if not _confirm_attendee(booking, event_data):
                logger.error(
                    "Google Calendar event %s created for booking %s but did not confirm "
                    "the client's attendee invite (%s) — check the connected account's guest/sharing settings.",
                    event_id, booking.id, booking.client.email,
                )
                return False, event_id, "Calendar event was created, but the client's invitation could not be confirmed."
            return True, event_id, None
        except Exception as exc:
            logger.exception("Failed to create Google Calendar event for booking %s", booking.id)
            return False, None, str(exc)

    @staticmethod
    def update_event(booking):
        if not booking.google_event_id:
            return GoogleCalendarService.create_event(booking)

        access_token, calendar_id, error = _get_access_token()
        if error:
            return False, None, error
        try:
            resp = requests.patch(
                f"{CALENDAR_API_BASE}/calendars/{calendar_id}/events/{booking.google_event_id}",
                params={"sendUpdates": "all"},
                headers={"Authorization": f"Bearer {access_token}"},
                json=_event_payload(booking),
                timeout=10,
            )
            if resp.status_code == 404:
                # The event was removed on the Google side out-of-band —
                # self-heal by creating a fresh one instead of failing.
                return GoogleCalendarService.create_event(booking)
            resp.raise_for_status()
            event_data = resp.json()
            event_id = event_data.get("id")
            if not _confirm_attendee(booking, event_data):
                logger.error(
                    "Google Calendar event %s updated for booking %s but did not confirm "
                    "the client's attendee invite (%s).",
                    event_id, booking.id, booking.client.email,
                )
                return False, event_id, "Calendar event was updated, but the client's invitation could not be confirmed."
            return True, event_id, None
        except Exception as exc:
            logger.exception("Failed to update Google Calendar event for booking %s", booking.id)
            return False, booking.google_event_id, str(exc)

    @staticmethod
    def delete_event(booking):
        if not booking.google_event_id:
            return True, None, None

        access_token, calendar_id, error = _get_access_token()
        if error:
            return False, booking.google_event_id, error
        try:
            resp = requests.delete(
                f"{CALENDAR_API_BASE}/calendars/{calendar_id}/events/{booking.google_event_id}",
                params={"sendUpdates": "all"},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            if resp.status_code not in (200, 204, 404, 410):
                resp.raise_for_status()
            return True, None, None
        except Exception as exc:
            logger.exception("Failed to delete Google Calendar event for booking %s", booking.id)
            return False, booking.google_event_id, str(exc)
