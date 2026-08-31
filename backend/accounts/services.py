"""Google identity verification and account-linking logic."""
import logging

import secrets
import smtplib
import socket
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


# One background retry for a transient, connection-level SMTP failure. This
# runs entirely inside the email worker thread -- NEVER in the
# request/response cycle -- so it can never slow the OTP API response. Kept
# to a single retry with a short fixed delay: enough to ride out a dropped
# or refused connection, not so much that a hard outage leaves a thread
# stuck for minutes.
OTP_EMAIL_MAX_ATTEMPTS = 2
OTP_EMAIL_RETRY_DELAY_SECONDS = 2

# Only connection-level failures that occur *before* the message body is
# handed to the server are retried -- retrying these cannot deliver a
# second copy of the code. Deliberately NOT a broad `OSError` /
# `smtplib.SMTPException`: those are base classes of the permanent,
# post-DATA failures (SMTPRecipientsRefused, SMTPSenderRefused,
# SMTPAuthenticationError, SMTPDataError, ...), which must fall through to
# the catch-all below and be logged once, never retried.
_RETRYABLE_SMTP_ERRORS = (
    smtplib.SMTPServerDisconnected,
    smtplib.SMTPConnectError,
    smtplib.SMTPHeloError,
    ConnectionError,   # reset / refused / broken pipe
    TimeoutError,      # socket timeout (also socket.timeout on 3.10+)
    socket.gaierror,   # DNS resolution failure
)


def _build_otp_message(email, code):
    """Render the templates and assemble the OTP email object.

    Pure CPU / template work with no network I/O. Called from the
    background worker thread (not the request thread) so template loading
    and parsing never touch the OTP API response path, and a template
    error can never turn an OTP request into a 500.

    `to=[email]` only -- the requesting user's own address is the sole
    recipient; no cc/bcc is ever set, so settings.ADMINS (the
    security-alert mailbox) can never receive an OTP.

    `reply_to=[EMAIL_HOST_USER]`: the same real, authenticated sending
    address as From -- an explicit, monitored reply address rather than
    none at all (a minor, legitimate deliverability signal; it does not
    disguise or change who the sender is).

    `headers={"Message-ID": ...}` anchored to the real sending domain
    (gmail.com) instead of Django's default, which builds it from the
    local/container hostname -- a meaningless, non-resolvable string that
    is itself a low-trust signal to spam classifiers.
    """
    context = {"code": code, "ttl_minutes": EmailOTP.TTL_MINUTES, "email": email}
    reply_to = [settings.EMAIL_HOST_USER] if settings.EMAIL_HOST_USER else None
    message = EmailMultiAlternatives(
        subject="Your CRM & Booking verification code",
        body=render_to_string("emails/otp_code.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
        reply_to=reply_to,
        headers={"Message-ID": make_msgid(domain="gmail.com")},
    )
    message.attach_alternative(render_to_string("emails/otp_code.html", context), "text/html")
    return message


def send_otp_email(email, code, otp_id=None, created_monotonic=None):
    """Deliver a freshly generated + persisted OTP code on a background
    thread, returning immediately so the request that triggered it never
    waits on SMTP.

    The code is already generated and persisted synchronously
    (EmailOTP.generate_for_email) before this is called -- the only thing
    left is delivery. Everything expensive (template rendering + the SMTP
    conversation with Gmail, typically 0.3-2s) happens on the worker
    thread; the request thread only spawns it. A slow or failing send can
    no longer eat into the 10-minute OTP window via a stalled HTTP request.

    Diagnostic timeline (INFO, structured, and it NEVER logs the code or
    the rendered body). All timings use time.monotonic() and, when
    `created_monotonic` is supplied by the caller, are anchored to the
    moment the OTP row was created so the whole path is measurable from
    one place:

        otp_created            (request thread, request_email_otp)
          -> email_task_queued   (request thread, here, just before .start())
          -> email_task_started  (worker thread, first line -- schedule_latency_ms
                                  is the OS/GIL hand-off delay, previously blind)
          -> smtp_send_started   (worker thread, per attempt)
          -> smtp_send_completed (worker thread -- since_otp_created_ms is the
                                  total application-side time to Gmail acceptance)

    Reading the gaps between these tells you exactly where a slow OTP is
    spent: task queue / worker scheduling / SMTP connection / provider.
    (This still cannot observe anything past Gmail *accepting* the
    message -- recipient-side delivery latency is not visible from here.)
    """
    queued_at = time.monotonic()
    origin = created_monotonic if created_monotonic is not None else queued_at

    def _log(event, level=logging.INFO, **fields):
        logger.log(level, event, extra={"event": event, "otp_id": otp_id, "email": email, **fields})

    def _send():
        try:
            started_at = time.monotonic()
            _log(
                "email_task_started",
                # The OS/GIL delay between the request thread queuing this
                # and the worker actually running -- the one segment that
                # used to be unmeasured. A consistently large value here
                # (vs. a large smtp_send_* duration) points at worker
                # scheduling under load, not the mail provider.
                schedule_latency_ms=round((started_at - queued_at) * 1000, 1),
                since_otp_created_ms=round((started_at - origin) * 1000, 1),
            )

            message = _build_otp_message(email, code)
            # The literal to/cc/bcc about to be handed to the SMTP backend,
            # read back off the constructed message object itself, so this
            # trace would still catch a recipient bug even if something
            # upstream mutated `to`.
            _log(
                "otp_email_recipient_resolved",
                to=message.to, cc=message.cc, bcc=message.bcc,
                from_email=message.from_email, reply_to=message.reply_to,
                message_id=message.extra_headers.get("Message-ID"),
            )

            for attempt in range(1, OTP_EMAIL_MAX_ATTEMPTS + 1):
                send_started_at = time.monotonic()
                _log(
                    "smtp_send_started",
                    attempt=attempt,
                    since_otp_created_ms=round((send_started_at - origin) * 1000, 1),
                )
                try:
                    message.send(fail_silently=False)
                except _RETRYABLE_SMTP_ERRORS as exc:
                    is_last = attempt >= OTP_EMAIL_MAX_ATTEMPTS
                    _log(
                        "smtp_send_failed" if is_last else "smtp_send_retry",
                        level=logging.ERROR if is_last else logging.WARNING,
                        attempt=attempt,
                        error=exc.__class__.__name__,
                        duration_ms=round((time.monotonic() - send_started_at) * 1000, 1),
                    )
                    if is_last:
                        return
                    # New Message-ID for the retried copy (RFC-correct for
                    # a resend, and avoids provider-side dedup dropping it).
                    message = _build_otp_message(email, code)
                    time.sleep(OTP_EMAIL_RETRY_DELAY_SECONDS)
                    continue
                _log(
                    "smtp_send_completed",
                    attempt=attempt,
                    duration_ms=round((time.monotonic() - send_started_at) * 1000, 1),
                    since_otp_created_ms=round((time.monotonic() - origin) * 1000, 1),
                )
                return
        except Exception:
            # A non-retryable SMTP error, a template error, or anything
            # unexpected: log it (never swallow silently) and let the
            # thread exit cleanly. The OTP row is untouched and still
            # valid -- the user can request a resend.
            logger.exception(
                "smtp_send_failed",
                extra={"event": "smtp_send_failed", "otp_id": otp_id, "email": email},
            )

    _log(
        "email_task_queued",
        since_otp_created_ms=round((queued_at - origin) * 1000, 1),
    )
    threading.Thread(target=_send, name=f"otp-email-{otp_id or 'x'}", daemon=True).start()


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

        otp_instance, raw_code = EmailOTP.generate_for_email(email)
        created_monotonic = time.monotonic()
        logger.info(
            "otp_created",
            extra={
                "event": "otp_created",
                "otp_id": otp_instance.id,
                "email": email,
                "created_at": otp_instance.created_at.isoformat(),
            },
        )
        # Hand off to the background email worker the instant the code is
        # safely persisted -- nothing (not even the cleanup DELETE below)
        # sits between "OTP saved" and "email queued".
        send_otp_email(email, raw_code, otp_id=otp_instance.id, created_monotonic=created_monotonic)

        # Opportunistic cleanup: bound row growth without a background job.
        # Runs after the email hand-off -- it is best-effort housekeeping
        # and must never delay delivery of the code we just issued. (The
        # row just created is never matched: it is unexpired and unconsumed.)
        EmailOTP.objects.filter(email=email).filter(
            Q(expires_at__lt=now) | Q(consumed_at__isnull=False)
        ).delete()
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
