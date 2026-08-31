"""SecurityFeatures.md F-9 — routes the specific high-value conditions the
audit called out to a real, owned destination (settings.ADMINS, via
Django's own mail_admins) so they don't just sit unread in the `security`
log stream core/audit.py produces.

Rate-based alerts (failed logins, booking-cancellation spikes) use the
default cache as a counter — the same pattern _bump_version already uses
elsewhere in this codebase. That means, same as H-5's throttle, this is
only accurate cluster-wide once L-5 (a shared cache backend) is fixed; on
today's per-process LocMemCache each worker counts independently.

Every alert is deduplicated per (kind, key) for ALERT_DEDUPE_WINDOW_SECONDS
so a burst of the same condition sends one email, not one per event — a
human only needs to be told once to go look.
"""

import logging
import threading

from django.core.cache import cache
from django.core.mail import mail_admins

logger = logging.getLogger("security")

ALERT_DEDUPE_WINDOW_SECONDS = 15 * 60

FAILED_LOGIN_THRESHOLD = 5
FAILED_LOGIN_WINDOW_SECONDS = 5 * 60

BOOKING_CANCELLATION_THRESHOLD = 5
BOOKING_CANCELLATION_WINDOW_SECONDS = 60 * 60


def _send_alert(kind, subject, message, dedupe_key=None):
    """Never raises — an alerting failure must not break the request or
    business action that triggered it.

    The dedupe check/set stays synchronous (it must run in-order relative to
    other callers to actually dedupe). Only the mail_admins() SMTP
    conversation is backgrounded, on the same fire-and-forget thread pattern
    already used for OTP email (accounts/services.py::send_otp_email) — so a
    slow or bouncing send to the admin mailbox can no longer add latency to
    whatever user-facing request triggered the alert. A failure here still
    only logs, never raises (the send runs in a try/except on that daemon
    thread).
    """
    try:
        cache_key = f"security_alert_sent_{kind}_{dedupe_key}" if dedupe_key else None
        if cache_key and cache.get(cache_key):
            return
        if cache_key:
            cache.set(cache_key, True, timeout=ALERT_DEDUPE_WINDOW_SECONDS)

        def _send():
            try:
                # fail_silently=False so a rejected send (e.g. Brevo 535 bad
                # SMTP key / 550 unverified SERVER_EMAIL sender) raises here
                # and is logged with its full traceback below, instead of
                # vanishing. Still never propagates: this whole body runs on
                # a daemon thread inside try/except, so the triggering
                # request is unaffected either way.
                mail_admins(subject, message, fail_silently=False)
                logger.warning("security_alert", extra={"event": "security_alert", "kind": kind, "subject": subject})
            except Exception:
                logger.exception("Failed to send security alert kind=%s", kind)

        threading.Thread(target=_send, daemon=True).start()
    except Exception:
        logger.exception("Failed to send security alert kind=%s", kind)


def alert_on_login_failure(identifier, ip):
    """Rate-based: N failed logins for the same submitted identifier OR the
    same source IP within the window (F-9: 'failed-authentication rate per
    IP and per account')."""
    for scope, key in (("account", identifier), ("ip", ip)):
        if not key:
            continue
        counter_key = f"failed_login_count_{scope}_{key}"
        count = cache.get(counter_key, 0) + 1
        cache.set(counter_key, count, timeout=FAILED_LOGIN_WINDOW_SECONDS)
        if count >= FAILED_LOGIN_THRESHOLD:
            _send_alert(
                "failed_login_rate",
                f"[Security] {count} failed logins for {scope}={key}",
                f"{count} failed login attempts for {scope}={key} within "
                f"{FAILED_LOGIN_WINDOW_SECONDS} seconds.",
                dedupe_key=f"{scope}_{key}",
            )


def alert_on_authorization_denied(actor_email, view_name, path):
    """F-9: 'any authorization denial for a staff-only route'. Every route
    in this app that can 403 is staff/admin-gated (accounts.permissions'
    IsStaffMember/IsAdmin/IsAdminOrReadOnly), so every 403 qualifies."""
    _send_alert(
        "authorization_denied",
        f"[Security] Authorization denied: {view_name}",
        f"{actor_email or 'anonymous'} was denied access to {view_name} ({path}).",
        dedupe_key=f"{actor_email or 'anonymous'}_{view_name}",
    )


def alert_on_role_change(action, actor_email, changes):
    """F-9: 'any TeamRoleAssignment change'."""
    _send_alert(
        "role_change",
        f"[Security] Team role {action}",
        f"{actor_email or 'system'} performed {action}: {changes}",
    )


def alert_on_invoice_void_or_refund(action, actor_email, invoice_repr, changes):
    """F-9: 'any invoice void or refund' — deliberately not pay/unpaid,
    which are routine daily operations, not the sensitive ones the audit
    flagged."""
    _send_alert(
        "invoice_void_or_refund",
        f"[Security] Invoice {action}: {invoice_repr}",
        f"{actor_email or 'system'} performed {action} on {invoice_repr}: {changes}",
    )


def alert_on_booking_cancellation_spike():
    """Rate-based: N cancellations within the window (F-9: 'any spike in
    booking cancellations' — these drive outbound waitlist mail per M-5, so
    a spike is itself worth knowing about, not just each individual cancel)."""
    counter_key = "booking_cancellation_count"
    count = cache.get(counter_key, 0) + 1
    cache.set(counter_key, count, timeout=BOOKING_CANCELLATION_WINDOW_SECONDS)
    if count >= BOOKING_CANCELLATION_THRESHOLD:
        _send_alert(
            "booking_cancellation_spike",
            f"[Security] {count} booking cancellations in the last hour",
            f"{count} bookings were cancelled within {BOOKING_CANCELLATION_WINDOW_SECONDS} seconds.",
            dedupe_key="spike",
        )
