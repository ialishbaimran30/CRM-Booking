"""Google identity verification and account-linking logic."""
import logging

import secrets
import threading
import time
import uuid
from email.utils import make_msgid

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import slugify
from google.auth import exceptions as google_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

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


def send_otp_email(email, code, otp_id=None):
    """Email a freshly generated OTP code using the app's existing SMTP config.

    The code is already generated and persisted (EmailOTP.generate_for_email,
    called just before this) before this function runs — the only thing left
    is delivery, which was previously the single biggest contributor to
    request latency on otp/request: a synchronous SMTP conversation with
    Gmail (typically 1-3s, unbounded before EMAIL_TIMEOUT was added) ran
    inline in the request/response cycle. Sent on a background thread
    instead — matching the existing fire-and-forget pattern already used for
    booking-confirmation email in booking/views.py — so the request returns
    to the caller immediately once the code is safely stored, rather than
    waiting on mail delivery. A slow/failed send no longer eats into the
    10-minute OTP window via a stalled HTTP request.

    Sent directly via EmailMultiAlternatives (plain text + HTML), the same
    pattern already used for every other transactional email in this app
    (see booking/emails.py), instead of the old bare single-part
    `send_mail` used before — Gmail's abuse heuristics treat a well-formed
    multipart message from an established pattern with more trust than a
    single-part, single-line, numeric-code-only message, which is a known
    contributor to the 550 5.7.1 "likely unsolicited" bounce this replaces.
    `to=[email]` only — no cc/bcc, ever: the requesting user's own address
    is the sole recipient, and the admin/security-alert mailbox (settings
    .ADMINS) is never added here.

    Diagnostic timing (never logs the code/template body itself): logs task
    start, SMTP send start, and send completion/failure with an elapsed
    duration, using time.monotonic() so the measurement can't be skewed by
    clock adjustments. `otp_id`/`email` are included only to correlate the
    handful of log lines for one OTP request — this can't observe anything
    past Gmail accepting the message (i.e. whether Gmail was slow to accept
    it from us vs. slow to hand it to the recipient afterwards), but a long
    duration here would point at the former.
    """
    context = {"code": code, "ttl_minutes": EmailOTP.TTL_MINUTES, "email": email}
    subject = "Your CRM & Booking verification code"
    text_body = render_to_string("emails/otp_code.txt", context)
    html_body = render_to_string("emails/otp_code.html", context)

    def _send():
        task_started_at = time.monotonic()
        logger.info(
            "otp_email_task_started",
            extra={"event": "otp_email_task_started", "otp_id": otp_id, "email": email},
        )

        send_started_at = time.monotonic()
        logger.info(
            "otp_email_smtp_send_started",
            extra={
                "event": "otp_email_smtp_send_started",
                "otp_id": otp_id,
                "email": email,
                "queue_delay_ms": round((send_started_at - task_started_at) * 1000, 1),
            },
        )
        try:
            # to=[email] only -- the requesting user's own address is the
            # sole recipient; no cc/bcc is ever set, so settings.ADMINS
            # (the security-alert mailbox) can never receive an OTP.
            #
            # reply_to=[EMAIL_HOST_USER]: same real, authenticated sending
            # address as From -- not a new identity, just an explicit,
            # transparent, monitored reply address instead of none at all
            # (a real Reply-To is a minor, legitimate deliverability signal;
            # this does not disguise or change who the sender is).
            #
            # headers={"Message-ID": ...}: Django's own default builds the
            # Message-ID's domain from the server's local hostname
            # (socket.getfqdn()) -- on a container host that's a meaningless,
            # non-resolvable string (verified locally: "LAPTOP-HDV357JO"),
            # which is itself a low-trust signal to spam classifiers. Using
            # the real sending domain (gmail.com) instead is honest -- that
            # literally is where this mail originates -- and removes that
            # specific red flag.
            reply_to = [settings.EMAIL_HOST_USER] if settings.EMAIL_HOST_USER else None
            message = EmailMultiAlternatives(
                subject=subject,
                body=text_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[email],
                reply_to=reply_to,
                headers={"Message-ID": make_msgid(domain="gmail.com")},
            )
            message.attach_alternative(html_body, "text/html")
            # Diagnostic trace point: the literal to/cc/bcc about to be
            # handed to the SMTP backend, read back off the constructed
            # message object itself (not the `email` variable) so this
            # would catch a bug even if something above mutated `to` in a
            # way this code doesn't otherwise account for.
            logger.info(
                "otp_email_recipient_resolved",
                extra={
                    "event": "otp_email_recipient_resolved",
                    "otp_id": otp_id,
                    "to": message.to,
                    "cc": message.cc,
                    "bcc": message.bcc,
                    "from_email": message.from_email,
                    "reply_to": message.reply_to,
                    "message_id": message.extra_headers.get("Message-ID"),
                },
            )
            message.send(fail_silently=False)
        except Exception:
            # Must never be silently swallowed: this is the only place a
            # real SMTP failure for an OTP send can be observed and logged.
            logger.exception(
                "otp_email_smtp_send_failed",
                extra={
                    "event": "otp_email_smtp_send_failed",
                    "otp_id": otp_id,
                    "email": email,
                    "duration_ms": round((time.monotonic() - send_started_at) * 1000, 1),
                },
            )
        else:
            logger.info(
                "otp_email_smtp_send_completed",
                extra={
                    "event": "otp_email_smtp_send_completed",
                    "otp_id": otp_id,
                    "email": email,
                    "duration_ms": round((time.monotonic() - send_started_at) * 1000, 1),
                },
            )

    threading.Thread(target=_send, daemon=True).start()


OTP_REQUEST_LOCK_SECONDS = 5


def request_email_otp(email):
    """Issue a new OTP for the given email, respecting the resend cooldown.

    Guarded by a short cache-based mutex, keyed per email, before the
    cooldown check: without it, two requests arriving within the same
    moment (a double-clicked resend button, a retried request) can both
    read the same "latest OTP" row before either has inserted its own, both
    pass the cooldown check, and both send a duplicate email — a race the
    cooldown alone doesn't close since it's a plain read-then-write with no
    locking. The mutex only serializes concurrent callers for this one
    email address; the 60s resend cooldown, MAX_ATTEMPTS and TTL logic
    below are unchanged.
    """
    email = email.strip().lower()
    lock_key = f"otp_request_lock_{email}"
    if not cache.add(lock_key, True, timeout=OTP_REQUEST_LOCK_SECONDS):
        # Someone else is already issuing a code for this email right now.
        raise OtpCooldownError(OTP_REQUEST_LOCK_SECONDS)

    try:
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

        otp_instance, raw_code = EmailOTP.generate_for_email(email)
        logger.info(
            "otp_created",
            extra={
                "event": "otp_created",
                "otp_id": otp_instance.id,
                "email": email,
                "created_at": otp_instance.created_at.isoformat(),
            },
        )
        send_otp_email(email, raw_code, otp_id=otp_instance.id)
    finally:
        cache.delete(lock_key)


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
