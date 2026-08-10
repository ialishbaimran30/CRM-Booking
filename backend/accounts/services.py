"""Google identity verification and account-linking logic."""
import logging

import secrets
import uuid

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify
from google.auth import exceptions as google_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from notifications.services import CommunicationService

from .models import EmailOTP, User

logger = logging.getLogger(__name__)


class GoogleTokenVerificationError(Exception):
    """The supplied token is malformed, expired, revoked, or otherwise invalid."""


class GoogleTokenVerificationUnavailable(Exception):
    """Google certificates could not be reached to verify the token."""


class GoogleAccountLinkError(Exception):
    """The email is already linked to a different Google account."""


def verify_google_id_token(raw_token):
    """Cryptographically verify a Google ID token and required identity claims."""
    client_id = settings.GOOGLE_OAUTH_CLIENT_ID
    if not client_id:
        raise ImproperlyConfigured("GOOGLE_OAUTH_CLIENT_ID is not configured.")

    try:
        claims = google_id_token.verify_oauth2_token(
            raw_token,
            google_requests.Request(),
            audience=client_id,
        )
    except google_exceptions.TransportError as exc:
        raise GoogleTokenVerificationUnavailable from exc
    except (ValueError, google_exceptions.GoogleAuthError) as exc:
        # The library verifies signature, issuer, audience and expiration.
        raise GoogleTokenVerificationError from exc

    email = claims.get("email")
    subject = claims.get("sub")
    email_verified = claims.get("email_verified") is True or claims.get("email_verified") == "true"
    if not email or not subject or not email_verified:
        raise GoogleTokenVerificationError

    try:
        validate_email(email)
    except Exception as exc:
        raise GoogleTokenVerificationError from exc

    return {
        "email": email.lower(),
        "subject": str(subject),
        "full_name": str(claims.get("name") or "").strip(),
        "picture": str(claims.get("picture") or "").strip(),
    }


def _google_username(subject, email):
    """Create a stable, unique username for a newly created Google account."""
    base = slugify(email.split("@", maxsplit=1)[0]) or "google-user"
    return f"{base}-{subject}"[:150]


@transaction.atomic
def authenticate_google_account(identity):
    """Find an account by Google subject or link/create it using verified email."""
    user = User.objects.select_for_update().filter(google_subject=identity["subject"]).first()
    if user:
        return user, False

    # A verified Google email may link to a pre-existing password account.
    user = User.objects.select_for_update().filter(email__iexact=identity["email"]).first()
    if user:
        if user.google_subject and user.google_subject != identity["subject"]:
            raise GoogleAccountLinkError
        user.google_subject = identity["subject"]
        user.email_verified = True
        if not user.profile_picture_url and identity["picture"]:
            user.profile_picture_url = identity["picture"]
        if not user.full_name and identity["full_name"]:
            user.full_name = identity["full_name"]
        user.save(update_fields=["google_subject", "email_verified", "profile_picture_url", "full_name"])
        return user, False

    user = User(
        username=_google_username(identity["subject"], identity["email"]),
        email=identity["email"],
        full_name=identity["full_name"],
        google_subject=identity["subject"],
        profile_picture_url=identity["picture"],
        email_verified=True,
    )
    user.set_unusable_password()
    user.save()
    return user, True


class OtpCooldownError(Exception):
    """A code was already sent recently; caller must wait before resending."""

    def __init__(self, retry_after_seconds):
        self.retry_after_seconds = retry_after_seconds
        super().__init__("OTP resend cooldown is still active.")


class OtpNotFoundError(Exception):
    """No usable (unconsumed, unexpired) OTP exists for this email."""


class OtpLockedError(Exception):
    """Too many incorrect attempts were made against the latest OTP."""


class OtpInvalidError(Exception):
    """The supplied code did not match."""

    def __init__(self, attempts_remaining):
        self.attempts_remaining = attempts_remaining
        super().__init__("OTP code did not match.")


def _otp_username(email):
    """Create a stable, unique username for a newly created OTP-only account."""
    base = slugify(email.split("@", maxsplit=1)[0]) or "user"
    for _ in range(5):
        candidate = f"{base}-{secrets.token_hex(4)}"[:150]
        if not User.objects.filter(username=candidate).exists():
            return candidate
    return f"{base}-{uuid.uuid4().hex[:12]}"[:150]


def send_otp_email(email, code):
    """Email a freshly generated OTP code using the app's existing SMTP config."""
    subject = "Your CRM & Booking verification code"
    message = (
        f"Your verification code is {code}. It expires in {EmailOTP.TTL_MINUTES} minutes. "
        "If you didn't request this, you can safely ignore this email."
    )
    CommunicationService.send_email_notification(subject, message, email)


def request_email_otp(email):
    """Issue a new OTP for the given email, respecting the resend cooldown."""
    email = email.strip().lower()
    now = timezone.now()

    latest = EmailOTP.objects.filter(email=email).order_by("-created_at").first()
    if latest and not latest.is_expired():
        elapsed = (now - latest.created_at).total_seconds()
        if elapsed < EmailOTP.RESEND_COOLDOWN_SECONDS:
            raise OtpCooldownError(int(EmailOTP.RESEND_COOLDOWN_SECONDS - elapsed))

    # Opportunistic cleanup: bound row growth without a background job.
    EmailOTP.objects.filter(email=email).filter(
        Q(expires_at__lt=now) | Q(consumed_at__isnull=False)
    ).delete()

    _, raw_code = EmailOTP.generate_for_email(email)
    send_otp_email(email, raw_code)


@transaction.atomic
def verify_email_otp(email, code):
    """Verify a submitted OTP and find-or-create the associated user account."""
    email = email.strip().lower()
    otp = (
        EmailOTP.objects.select_for_update()
        .filter(email=email, consumed_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if not otp or otp.is_expired():
        raise OtpNotFoundError

    if otp.attempt_count >= EmailOTP.MAX_ATTEMPTS:
        raise OtpLockedError

    if not otp.check_code(code):
        otp.attempt_count += 1
        otp.save(update_fields=["attempt_count"])
        raise OtpInvalidError(EmailOTP.MAX_ATTEMPTS - otp.attempt_count)

    otp.consumed_at = timezone.now()
    otp.save(update_fields=["consumed_at"])

    user = User.objects.select_for_update().filter(email__iexact=email).first()
    if user:
        created = False
        if not user.email_verified:
            user.email_verified = True
            user.save(update_fields=["email_verified"])
    else:
        user = User(
            username=_otp_username(email),
            email=email,
            email_verified=True,
        )
        user.set_unusable_password()
        user.save()
        created = True

    return user, created
