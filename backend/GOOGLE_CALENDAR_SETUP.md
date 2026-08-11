# Google Calendar sync backend setup

Every booking (Client, Booking Manager, or Admin) automatically creates/updates/cancels
an event on one shared business Google Calendar, inviting the client's Gmail so Google
emails them a normal calendar invite. Calendar failures never fail a booking — the CRM
database stays the source of truth (see `booking/google_calendar.py`).

## 1. Google Cloud Console

Reuses the same project/OAuth client as Google Sign-In (`GOOGLE_AUTH_SETUP.md`):

1. **APIs & Services → Library** → enable **Google Calendar API**.
2. **APIs & Services → Credentials** → open the existing Web application OAuth client.
3. Add an **Authorized redirect URI**: `http://localhost:8000/admin-tools/google-calendar/callback/`
   (and your production backend's equivalent URL).
4. Copy the client's **Client secret** — unlike the ID-token sign-in flow, this server-side
   flow requires it.

## 2. Environment variables

See `.env.example`:

```
GOOGLE_CALENDAR_CLIENT_ID=...        # defaults to GOOGLE_OAUTH_CLIENT_ID if unset
GOOGLE_CALENDAR_CLIENT_SECRET=...    # required
GOOGLE_CALENDAR_REDIRECT_URI=...     # must exactly match the Console redirect URI
GOOGLE_CALENDAR_ID=primary           # "primary" = the connected account's main calendar
```

## 3. One-time authorization (Admin only)

1. Log into Django admin (`/admin/`) as a staff user, using the **business** Google
   account's own credentials (or any staff account — the account you authorize with
   Google in the next step is the one whose calendar receives every event).
2. Visit `/admin-tools/google-calendar/connect/`.
3. Sign in with the business Google account and grant the "manage events" permission
   (scope `.../auth/calendar.events` only — least privilege, no calendar admin access).
4. You're redirected back to **Booking → Google calendar credentials** in Django admin,
   showing the connected email and timestamp. The refresh token is encrypted at rest and
   never exposed via any API or to the frontend.
5. To reconnect (e.g. after revoking access), just repeat step 2 — it replaces the stored
   credential.

## 4. What gets synced

- **Create**: new booking → new Calendar event, client added as an attendee (Google
  emails them the invite).
- **Update/reschedule**: existing event is patched in place — never duplicated. The
  booking's `google_event_id` is the single source of truth for this.
- **Cancel**: the Calendar event is deleted; the CRM's own cancellation email/notification
  is unaffected.
- **Hard delete**: the Calendar event is removed before the CRM row is deleted.

## 5. Failure handling

If Calendar sync fails (not connected, revoked/expired token, network error), the booking
still succeeds. `Booking.calendar_sync_status` is set to `FAILED` and the technical error is
logged server-side (`Booking.calendar_sync_error`, never returned to the frontend). The
frontend shows a generic "Calendar synchronization is pending." toast instead of the raw error.
