import threading
from datetime import date, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import TeamRoleAssignment, User
from booking.models import Booking
from clients.models import Client
from payments.models import Invoice
from payments.services import BillingService

from . import alerting
from .audit import record_audit_event
from .models import AuditLog


def make_user(email, password="test-pass-12345"):
    return User.objects.create_user(username=email.split("@")[0], email=email, password=password)


def make_staff(email, role="Booking Manager", password="test-pass-12345"):
    user = make_user(email, password)
    TeamRoleAssignment.objects.create(role_name=role, assigned_user=user)
    return user


def _join_background_threads():
    """core.alerting._send_alert now sends mail_admins() on a background
    daemon thread (matching accounts/services.py::send_otp_email), so it no
    longer blocks the caller. Tests that assert on mail.outbox right after
    triggering an alert need to wait for that thread to actually finish
    first, or they'd be racing it."""
    for t in threading.enumerate():
        if t is not threading.main_thread():
            t.join(timeout=2)


def find_event(records, event):
    """`assertLogs` captures raw LogRecord objects, not JSONFormatter's
    rendered output (that formatter only runs on the real stdout handler) —
    so assert against the `extra={...}` attributes attached to the record
    itself, e.g. record.outcome, record.actor_id, set by log_security_event."""
    for record in records:
        if getattr(record, "event", None) == event:
            return record
    return None


class RecordAuditEventTests(TestCase):
    """core.audit.record_audit_event — the AuditLog write path itself."""

    def test_records_actor_and_target_snapshot(self):
        actor = make_user("actor@example.com")
        client = Client.objects.create(full_name="Jane Doe", email="jane@example.com")

        record_audit_event(
            actor=actor, action=AuditLog.Action.CLIENT_CREATED, target=client,
            changes={"email": client.email},
        )

        entry = AuditLog.objects.get()
        self.assertEqual(entry.actor_id, actor.id)
        self.assertEqual(entry.actor_email, actor.email)
        self.assertEqual(entry.action, AuditLog.Action.CLIENT_CREATED)
        self.assertEqual(entry.target_type, "Client")
        self.assertEqual(entry.target_id, str(client.pk))
        self.assertEqual(entry.changes, {"email": client.email})

    def test_survives_a_deleted_actor(self):
        # AuditLog.actor is SET_NULL — the row, and the actor_email snapshot,
        # must outlive the User row it was written for.
        actor = make_user("gone@example.com")
        record_audit_event(actor=actor, action=AuditLog.Action.CLIENT_DELETED, target=None)
        actor.delete()

        entry = AuditLog.objects.get()
        self.assertIsNone(entry.actor_id)
        self.assertEqual(entry.actor_email, "gone@example.com")

    def test_never_raises_on_anonymous_actor(self):
        record_audit_event(actor=None, action=AuditLog.Action.CLIENT_CREATED, target=None)
        entry = AuditLog.objects.get()
        self.assertIsNone(entry.actor)
        self.assertEqual(entry.actor_email, "")


class LoginSecurityLoggingTests(TestCase):
    """LoggingTokenObtainPairSerializer — H-5's throttled login view, F-1's
    logging of every attempt. The custom User model's USERNAME_FIELD is the
    inherited default, 'username'."""

    def setUp(self):
        self.api_client = APIClient()
        self.user = make_user("staffmember@example.com")

    def test_failed_login_is_logged_without_leaking_the_password(self):
        with self.assertLogs("security", level="INFO") as cm:
            response = self.api_client.post(
                "/api/accounts/login/",
                {"username": self.user.username, "password": "totally-wrong"},
                format="json",
            )
        self.assertEqual(response.status_code, 401)
        record = find_event(cm.records, "login")
        self.assertIsNotNone(record)
        self.assertEqual(record.outcome, "failure")
        self.assertNotIn("totally-wrong", "\n".join(cm.output))

    def test_successful_login_is_logged(self):
        with self.assertLogs("security", level="INFO") as cm:
            response = self.api_client.post(
                "/api/accounts/login/",
                {"username": self.user.username, "password": "test-pass-12345"},
                format="json",
            )
        self.assertEqual(response.status_code, 200)
        record = find_event(cm.records, "login")
        self.assertIsNotNone(record)
        self.assertEqual(record.outcome, "success")
        self.assertEqual(record.actor_id, self.user.id)


class OtpSecurityLoggingTests(TestCase):
    def setUp(self):
        self.api_client = APIClient()

    @patch("accounts.views.request_email_otp")
    def test_otp_request_success_is_logged(self, mock_request):
        with self.assertLogs("security", level="INFO") as cm:
            response = self.api_client.post("/api/accounts/otp/request/", {"email": "x@example.com"}, format="json")
        self.assertEqual(response.status_code, 200)
        record = find_event(cm.records, "otp_request")
        self.assertIsNotNone(record)
        self.assertEqual(record.outcome, "success")

    @patch("accounts.views.verify_email_otp")
    def test_otp_verify_success_is_logged(self, mock_verify):
        user = make_user("otpuser@example.com")
        mock_verify.return_value = (user, False)

        with self.assertLogs("security", level="INFO") as cm:
            response = self.api_client.post(
                "/api/accounts/otp/verify/", {"email": user.email, "code": "123456"}, format="json"
            )
        self.assertEqual(response.status_code, 200)
        record = find_event(cm.records, "otp_verify")
        self.assertIsNotNone(record)
        self.assertEqual(record.outcome, "success")

    def test_otp_verify_failure_is_logged_without_leaking_the_code(self):
        with self.assertLogs("security", level="INFO") as cm:
            response = self.api_client.post(
                "/api/accounts/otp/verify/", {"email": "nouser@example.com", "code": "000000"}, format="json"
            )
        self.assertEqual(response.status_code, 401)
        record = find_event(cm.records, "otp_verify")
        self.assertIsNotNone(record)
        self.assertEqual(record.outcome, "failure")
        self.assertNotIn("000000", "\n".join(cm.output))


class AuthorizationDeniedLoggingTests(TestCase):
    """core.exceptions.logging_exception_handler — every 403 across every
    view, exercised here via H-1's now-staff-only resources endpoint."""

    def test_403_is_logged(self):
        client_user = make_user("plainclient@example.com")
        api_client = APIClient()
        api_client.force_authenticate(user=client_user)

        with self.assertLogs("security", level="INFO") as cm:
            response = api_client.get("/api/resources/staff/")
        self.assertEqual(response.status_code, 403)
        record = find_event(cm.records, "authorization_denied")
        self.assertIsNotNone(record)
        self.assertEqual(record.actor_id, client_user.id)


class TeamRoleAuditTests(TestCase):
    """AuditLog trail for role assignment changes (F-1's top example)."""

    def test_role_assignment_and_removal_are_audited(self):
        admin = make_staff("admin1@example.com", role="Admin")
        bm_user = make_user("bm-candidate@example.com")

        api_client = APIClient()
        api_client.force_authenticate(user=admin)

        response = api_client.post(
            "/api/accounts/team-roles/",
            {"role_name": "Booking Manager", "assigned_user_id": bm_user.id},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        created_entry = AuditLog.objects.get(action=AuditLog.Action.ROLE_ASSIGNED)
        self.assertEqual(created_entry.actor_id, admin.id)
        self.assertEqual(created_entry.changes["assigned_user_email"], bm_user.email)

        role_id = response.data["id"]
        response = api_client.delete(f"/api/accounts/team-roles/{role_id}/")
        self.assertEqual(response.status_code, 204)
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.ROLE_REMOVED).exists())


class ClientAuditTests(TestCase):
    """AuditLog trail for Client create/update/delete."""

    def test_client_crud_is_audited(self):
        staff = make_staff("clientstaff@example.com")
        api_client = APIClient()
        api_client.force_authenticate(user=staff)

        response = api_client.post(
            "/api/clients/", {"full_name": "New Client", "email": "newclient@example.com"}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.CLIENT_CREATED).exists())

        client_id = response.data["id"]
        response = api_client.patch(f"/api/clients/{client_id}/", {"full_name": "Renamed Client"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.CLIENT_UPDATED).exists())

        response = api_client.delete(f"/api/clients/{client_id}/")
        self.assertEqual(response.status_code, 204)
        deleted_entry = AuditLog.objects.get(action=AuditLog.Action.CLIENT_DELETED)
        self.assertEqual(deleted_entry.changes["email"], "newclient@example.com")


class InvoiceAuditTests(TestCase):
    """AuditLog trail for the BillingService invoice actions (pay/unpaid/refund)."""

    def setUp(self):
        self.staff = make_staff("billingstaff@example.com", role="Admin")
        client_obj = Client.objects.create(full_name="Billing Client", email="billing@example.com")
        booking = Booking.objects.create(
            client=client_obj,
            service_name="Consultation",
            booking_date=date.today() + timedelta(days=1),
            start_time=time(10, 0),
            end_time=time(11, 0),
            price=Decimal("100.00"),
            created_by=self.staff,
        )
        self.invoice = BillingService.generate_invoice_for_booking(booking)

    def test_pay_unpaid_refund_are_each_audited(self):
        BillingService.mark_invoice_paid(self.invoice, payment_method="CASH", marked_by=self.staff)
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.INVOICE_PAID).exists())

        BillingService.mark_invoice_unpaid(self.invoice, marked_by=self.staff)
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.INVOICE_UNPAID).exists())

        BillingService.mark_invoice_paid(self.invoice, payment_method="CASH", marked_by=self.staff)
        BillingService.refund_invoice(self.invoice, reason="Client cancelled", marked_by=self.staff)
        refund_entry = AuditLog.objects.get(action=AuditLog.Action.INVOICE_REFUNDED)
        self.assertEqual(refund_entry.changes["reason"], "Client cancelled")
        self.assertEqual(refund_entry.actor_id, self.staff.id)


class BookingAuditTests(TestCase):
    """AuditLog trail for booking cancel (M-5) and staff-only delete (H-4)."""

    def setUp(self):
        self.staff = make_staff("bookingstaff@example.com")
        client_obj = Client.objects.create(full_name="Booking Client", email="bookingclient@example.com")
        self.booking = Booking.objects.create(
            client=client_obj,
            service_name="Consultation",
            booking_date=date.today() + timedelta(days=1),
            start_time=time(10, 0),
            end_time=time(11, 0),
            price=Decimal("100.00"),
            created_by=self.staff,
        )
        self.api_client = APIClient()
        self.api_client.force_authenticate(user=self.staff)

    def test_cancel_is_audited(self):
        response = self.api_client.patch(f"/api/bookings/{self.booking.id}/", {"status": "CANCELLED"}, format="json")
        self.assertEqual(response.status_code, 200)
        entry = AuditLog.objects.get(action=AuditLog.Action.BOOKING_CANCELLED)
        self.assertEqual(entry.changes["after_status"], "CANCELLED")

    def test_delete_is_audited(self):
        response = self.api_client.delete(f"/api/bookings/{self.booking.id}/")
        self.assertEqual(response.status_code, 204)
        entry = AuditLog.objects.get(action=AuditLog.Action.BOOKING_DELETED)
        self.assertEqual(entry.actor_id, self.staff.id)


@override_settings(ADMINS=[("Security Alert Recipient 1", "secalerts@example.com")])
class SecurityAlertingTests(TestCase):
    """core.alerting — SecurityFeatures.md F-9's rate-based and one-off
    alerts, routed to settings.ADMINS via Django's own mail_admins. Uses the
    default cache directly (same as production's counters), so each test
    clears it first to avoid cross-test contamination."""

    def setUp(self):
        cache.clear()
        mail.outbox = []

    def test_login_failure_alerts_once_the_account_scope_hits_threshold(self):
        # Same identifier, a different IP each call, so only the 'account'
        # scope — never 'ip' — can reach FAILED_LOGIN_THRESHOLD here.
        for i in range(alerting.FAILED_LOGIN_THRESHOLD):
            alerting.alert_on_login_failure("attacker@example.com", f"10.0.0.{i}")
        _join_background_threads()

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("failed logins", mail.outbox[0].subject)
        self.assertIn("account=attacker@example.com", mail.outbox[0].body)

    def test_login_failure_below_threshold_does_not_alert(self):
        for i in range(alerting.FAILED_LOGIN_THRESHOLD - 1):
            alerting.alert_on_login_failure("someone@example.com", f"10.1.0.{i}")
        _join_background_threads()
        self.assertEqual(len(mail.outbox), 0)

    def test_login_failure_alert_is_deduped_within_the_window(self):
        for i in range(alerting.FAILED_LOGIN_THRESHOLD):
            alerting.alert_on_login_failure("repeat-attacker@example.com", f"10.2.0.{i}")
        _join_background_threads()
        self.assertEqual(len(mail.outbox), 1)

        # A burst reporting the same condition again must not re-alert
        # within the dedupe window — one email, not one per event.
        alerting.alert_on_login_failure("repeat-attacker@example.com", "10.2.0.99")
        _join_background_threads()
        self.assertEqual(len(mail.outbox), 1)

    def test_authorization_denied_alerts_immediately(self):
        alerting.alert_on_authorization_denied("client@example.com", "StaffViewSet", "/api/resources/staff/")
        _join_background_threads()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("StaffViewSet", mail.outbox[0].subject)

    def test_role_change_alerts_immediately(self):
        alerting.alert_on_role_change(AuditLog.Action.ROLE_ASSIGNED, "admin@example.com", {"role_name": "Admin"})
        _join_background_threads()
        self.assertEqual(len(mail.outbox), 1)

    def test_invoice_void_or_refund_alerts_immediately(self):
        alerting.alert_on_invoice_void_or_refund(
            "refunded", "admin@example.com", "Invoice #INV-1", {"reason": "test"}
        )
        _join_background_threads()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("refunded", mail.outbox[0].subject)

    def test_booking_cancellation_spike_alerts_only_at_threshold(self):
        for _ in range(alerting.BOOKING_CANCELLATION_THRESHOLD - 1):
            alerting.alert_on_booking_cancellation_spike()
        _join_background_threads()
        self.assertEqual(len(mail.outbox), 0)

        alerting.alert_on_booking_cancellation_spike()
        _join_background_threads()
        self.assertEqual(len(mail.outbox), 1)

    def test_never_raises_when_admins_unconfigured(self):
        with override_settings(ADMINS=[]):
            alerting.alert_on_role_change(AuditLog.Action.ROLE_REMOVED, "x@example.com", {})
            _join_background_threads()
        # No assertion beyond "didn't raise" — an empty ADMINS list must
        # degrade to a silent no-op, not an error.


class RoleChangeAlertIntegrationTests(TestCase):
    """Confirms the TeamManagementViewSet call sites actually trigger
    core.alerting, not just that the functions work in isolation."""

    @override_settings(ADMINS=[("Security Alert Recipient 1", "secalerts@example.com")])
    def test_assigning_and_removing_a_role_sends_an_alert(self):
        cache.clear()
        mail.outbox = []
        admin = make_staff("rolealertadmin@example.com", role="Admin")
        bm_user = make_user("rolealertcandidate@example.com")

        api_client = APIClient()
        api_client.force_authenticate(user=admin)

        response = api_client.post(
            "/api/accounts/team-roles/",
            {"role_name": "Booking Manager", "assigned_user_id": bm_user.id},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 1)

        role_id = response.data["id"]
        response = api_client.delete(f"/api/accounts/team-roles/{role_id}/")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(len(mail.outbox), 2)
