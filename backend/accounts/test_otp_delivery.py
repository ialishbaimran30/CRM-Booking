"""OTP email delivery-latency optimisation — focused coverage.

Verifies the properties the optimisation is responsible for:

* the OTP API response is returned *before* SMTP runs (never blocks),
* OTP generation / save stays synchronous and reliable,
* the full diagnostic timeline fires, in order, with monotonic timings,
* a transient connection-level SMTP failure is retried exactly once, in
  the background, and then delivered,
* a permanent SMTP failure is logged (never raised, never crashes the
  worker) and leaves the OTP row usable,
* the generated code still verifies, and the resend cooldown / expiry /
  opportunistic cleanup still hold.

The pre-existing OTP generation / verification / expiry / recipient /
concurrency behaviour is covered by ``accounts/tests.py`` and is unchanged
by this work.
"""
import smtplib
import socket
import threading
import time
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import EmailOTP
from .services import (
    OTP_EMAIL_MAX_ATTEMPTS,
    OtpCooldownError,
    OtpInvalidError,
    OtpNotFoundError,
    request_email_otp,
    verify_email_otp,
)

_ORIG_SEND = EmailMultiAlternatives.send


def _join_email_workers(timeout=5):
    """Wait for the fire-and-forget OTP email threads to finish, exactly as
    accounts/tests.py does, so assertions on mail.outbox / logs are stable."""
    for t in threading.enumerate():
        if t is not threading.main_thread():
            t.join(timeout=timeout)


def _events(records):
    return [getattr(r, "event", None) for r in records]


class OtpApiIsNonBlockingTests(TestCase):
    def setUp(self):
        cache.clear()
        mail.outbox = []

    def test_response_returns_before_the_email_is_sent(self):
        """The OTP row is written synchronously and the API responds, while
        the SMTP send is still pending on the worker thread."""
        release = threading.Event()

        def _gated_send(msg_self, *args, **kwargs):
            release.wait(timeout=5)  # hold the worker until the test lets it through
            return _ORIG_SEND(msg_self, *args, **kwargs)

        client = APIClient()
        with patch.object(EmailMultiAlternatives, "send", _gated_send):
            started = time.monotonic()
            resp = client.post(
                "/api/accounts/otp/request/",
                {"email": "nonblocking@example.com", "purpose": "signup"},
                format="json",
            )
            elapsed = time.monotonic() - started

            self.assertEqual(resp.status_code, 200)
            # Generation + save happened synchronously ...
            self.assertEqual(
                EmailOTP.objects.filter(email="nonblocking@example.com").count(), 1
            )
            # ... but the email has NOT been sent: the worker is still
            # blocked and the response already came back.
            self.assertEqual(len(mail.outbox), 0)
            self.assertLess(elapsed, 5.0, "OTP request must not wait on SMTP")

            release.set()
            _join_email_workers()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["nonblocking@example.com"])


class OtpDiagnosticTimelineTests(TestCase):
    def setUp(self):
        cache.clear()
        mail.outbox = []

    def test_full_timeline_is_emitted_in_order_with_timings(self):
        with self.assertLogs("accounts.services", level="INFO") as cap:
            request_email_otp("timeline@example.com")
            _join_email_workers()

        events = _events(cap.records)
        expected = [
            "otp_created",
            "email_task_queued",
            "email_task_started",
            "smtp_send_started",
            "smtp_send_completed",
        ]
        for name in expected:
            self.assertIn(name, events, f"{name!r} missing from timeline {events}")

        positions = [events.index(name) for name in expected]
        self.assertEqual(positions, sorted(positions), f"timeline out of order: {events}")

        started = next(
            r for r in cap.records if getattr(r, "event", None) == "email_task_started"
        )
        self.assertIsInstance(started.schedule_latency_ms, float)
        self.assertGreaterEqual(started.schedule_latency_ms, 0.0)

        completed = next(
            r for r in cap.records if getattr(r, "event", None) == "smtp_send_completed"
        )
        self.assertGreaterEqual(completed.since_otp_created_ms, 0.0)
        self.assertEqual(completed.attempt, 1)

    def test_code_never_appears_in_any_log_line(self):
        with patch("accounts.models.secrets.randbelow", return_value=246810):
            with self.assertLogs("accounts.services", level="INFO") as cap:
                request_email_otp("nolog2@example.com")
                _join_email_workers()
        for record in cap.records:
            self.assertNotIn("246810", record.getMessage())
            self.assertNotIn("246810", str(record.__dict__))


class OtpBackgroundRetryTests(TestCase):
    def setUp(self):
        cache.clear()
        mail.outbox = []

    def test_transient_connection_error_is_retried_once_then_delivered(self):
        calls = {"n": 0}

        def _flaky_send(msg_self, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise smtplib.SMTPServerDisconnected("connection dropped mid-handshake")
            return _ORIG_SEND(msg_self, *args, **kwargs)

        with patch("accounts.services.OTP_EMAIL_RETRY_DELAY_SECONDS", 0):
            with patch.object(EmailMultiAlternatives, "send", _flaky_send):
                with self.assertLogs("accounts.services", level="INFO") as cap:
                    request_email_otp("retry@example.com")
                    _join_email_workers()

        events = _events(cap.records)
        self.assertIn("smtp_send_retry", events)
        self.assertIn("smtp_send_completed", events)
        self.assertEqual(calls["n"], 2, "should be exactly one retry")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["retry@example.com"])

    def test_retry_count_is_bounded_and_never_loops(self):
        calls = {"n": 0}

        def _always_disconnect(msg_self, *args, **kwargs):
            calls["n"] += 1
            raise smtplib.SMTPServerDisconnected("still down")

        with patch("accounts.services.OTP_EMAIL_RETRY_DELAY_SECONDS", 0):
            with patch.object(EmailMultiAlternatives, "send", _always_disconnect):
                with self.assertLogs("accounts.services", level="INFO") as cap:
                    request_email_otp("down@example.com")  # must not raise
                    _join_email_workers()

        self.assertEqual(calls["n"], OTP_EMAIL_MAX_ATTEMPTS)
        self.assertIn("smtp_send_failed", _events(cap.records))
        self.assertEqual(len(mail.outbox), 0)
        # The code is still valid — the user can request a resend.
        self.assertEqual(EmailOTP.objects.filter(email="down@example.com").count(), 1)

    def test_permanent_smtp_failure_is_logged_not_raised_and_not_retried(self):
        calls = {"n": 0}

        def _permanent_reject(msg_self, *args, **kwargs):
            calls["n"] += 1
            raise smtplib.SMTPRecipientsRefused({"perm@example.com": (550, b"blocked")})

        with patch.object(EmailMultiAlternatives, "send", _permanent_reject):
            with self.assertLogs("accounts.services", level="INFO") as cap:
                request_email_otp("perm@example.com")  # must not raise
                _join_email_workers()

        self.assertEqual(calls["n"], 1, "permanent failures are not retried")
        self.assertIn("smtp_send_failed", _events(cap.records))
        self.assertEqual(EmailOTP.objects.filter(email="perm@example.com").count(), 1)

    def test_dns_failure_on_connect_is_retryable(self):
        calls = {"n": 0}

        def _dns_then_ok(msg_self, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise socket.gaierror("Name or service not known")
            return _ORIG_SEND(msg_self, *args, **kwargs)

        with patch("accounts.services.OTP_EMAIL_RETRY_DELAY_SECONDS", 0):
            with patch.object(EmailMultiAlternatives, "send", _dns_then_ok):
                request_email_otp("dns@example.com")
                _join_email_workers()

        self.assertEqual(calls["n"], 2)
        self.assertEqual(len(mail.outbox), 1)


class OtpPipelineUnchangedTests(TestCase):
    """Guard-rails: the optimisation must not have altered generation,
    verification, expiry, resend cooldown, or opportunistic cleanup."""

    def setUp(self):
        cache.clear()
        mail.outbox = []

    def test_generated_code_still_verifies_end_to_end(self):
        with patch("accounts.models.secrets.randbelow", return_value=424242):
            request_email_otp("verify@example.com")
            _join_email_workers()

        with self.assertRaises(OtpInvalidError):
            verify_email_otp("verify@example.com", "000000")

        user, created = verify_email_otp("verify@example.com", "424242")
        self.assertTrue(created)
        self.assertTrue(user.email_verified)

    def test_resend_cooldown_still_enforced_after_reordering_cleanup(self):
        request_email_otp("cooldown@example.com")
        _join_email_workers()
        with self.assertRaises(OtpCooldownError) as ctx:
            request_email_otp("cooldown@example.com")
        self.assertGreater(ctx.exception.retry_after_seconds, 5)

    def test_expiry_is_still_enforced(self):
        with patch("accounts.models.secrets.randbelow", return_value=111222):
            request_email_otp("expired@example.com")
            _join_email_workers()

        row = EmailOTP.objects.get(email="expired@example.com")
        row.expires_at = timezone.now() - timedelta(seconds=1)
        row.save(update_fields=["expires_at"])

        with self.assertRaises(OtpNotFoundError):
            verify_email_otp("expired@example.com", "111222")

    def test_opportunistic_cleanup_still_runs_after_the_email_handoff(self):
        stale, _ = EmailOTP.generate_for_email("cleanup@example.com")
        stale.expires_at = timezone.now() - timedelta(minutes=1)  # expired -> skips cooldown
        stale.consumed_at = timezone.now()
        stale.save(update_fields=["expires_at", "consumed_at"])

        cache.clear()
        request_email_otp("cleanup@example.com")
        _join_email_workers()

        rows = EmailOTP.objects.filter(email="cleanup@example.com")
        self.assertEqual(rows.count(), 1, "the stale row should have been purged")
        self.assertIsNone(rows.first().consumed_at)
