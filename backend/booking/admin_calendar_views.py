"""One-time Admin OAuth handshake that authorizes the business Google
account for Calendar sync. Plain Django views (session-authenticated via the
existing Django admin login), completely separate from the JWT `/api/`
surface — the refresh token this produces never touches React.
"""
import logging
import secrets
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.shortcuts import redirect

from .crypto import encrypt_token
from .google_calendar import CALENDAR_SCOPE
from .models import GoogleCalendarCredential

logger = logging.getLogger(__name__)

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v2/userinfo"
SESSION_STATE_KEY = "google_calendar_oauth_state"


@staff_member_required
def google_calendar_connect(request):
    """Redirect the logged-in Admin to Google's consent screen for the
    business account, authorizing Calendar access only (least privilege)."""
    state = secrets.token_urlsafe(32)
    request.session[SESSION_STATE_KEY] = state

    params = {
        "client_id": settings.GOOGLE_CALENDAR_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_CALENDAR_REDIRECT_URI,
        "response_type": "code",
        "scope": CALENDAR_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return redirect(f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}")


@staff_member_required
def google_calendar_callback(request):
    """Google redirects here with an authorization code. Exchanges it for a
    refresh token and stores it (encrypted) as the single Calendar
    credential every booking syncs to."""
    expected_state = request.session.pop(SESSION_STATE_KEY, None)
    returned_state = request.GET.get("state")
    code = request.GET.get("code")

    if not code or not expected_state or expected_state != returned_state:
        messages.error(request, "Google Calendar authorization failed: invalid or expired request.")
        return redirect("admin:booking_googlecalendarcredential_changelist")

    try:
        token_resp = requests.post(
            GOOGLE_TOKEN_ENDPOINT,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CALENDAR_CLIENT_ID,
                "client_secret": settings.GOOGLE_CALENDAR_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_CALENDAR_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        token_resp.raise_for_status()
        tokens = token_resp.json()
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            messages.error(
                request,
                "Google did not return a refresh token. Revoke this app's access at "
                "myaccount.google.com/permissions and try connecting again.",
            )
            return redirect("admin:booking_googlecalendarcredential_changelist")

        connected_email = ""
        try:
            userinfo_resp = requests.get(
                GOOGLE_USERINFO_ENDPOINT,
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
                timeout=10,
            )
            userinfo_resp.raise_for_status()
            connected_email = userinfo_resp.json().get("email", "")
        except Exception:
            logger.exception("Failed to fetch connected Google account email")

        GoogleCalendarCredential.objects.all().delete()
        GoogleCalendarCredential.objects.create(
            calendar_id=settings.GOOGLE_CALENDAR_ID,
            refresh_token_encrypted=encrypt_token(refresh_token),
            connected_email=connected_email,
            connected_by=request.user,
        )
        messages.success(request, f"Google Calendar connected ({connected_email or 'business account'}).")
    except Exception:
        logger.exception("Google Calendar OAuth callback failed")
        messages.error(request, "Google Calendar authorization failed. Check the server logs for details.")

    return redirect("admin:booking_googlecalendarcredential_changelist")
