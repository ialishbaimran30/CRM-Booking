from io import StringIO
from unittest.mock import patch

import pyotp
from django.core import mail
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from clients.models import Client
from core.models import AuditLog

from .management.commands.ensure_admin_seat import ADMIN_EMAIL
from .models import EmailOTP, TeamRoleAssignment, TOTPDevice, User
from .permissions import get_user_role
from .views import _provision_client_if_unstaffed


@override_settings(GOOGLE_OAUTH_CLIENT_ID="test-client.apps.googleusercontent.com")
class GoogleSignInViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/auth/google/"
        self.identity = {
            "email": "person@example.com",
            "subject": "google-subject-123",
            "full_name": "Test Person",
            "picture": "https://example.com/avatar.jpg",
        }

    @patch("accounts.views.verify_google_id_token")
    def test_creates_google_user_and_returns_jwts(self, verify_token):
        verify_token.return_value = self.identity

        response = self.client.post(self.url, {"id_token": "google-id-token"}, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user"]["email"], self.identity["email"])
        user = User.objects.get(email=self.identity["email"])
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.google_subject, self.identity["subject"])

    @patch("accounts.views.verify_google_id_token")
    def test_links_a_matching_password_account(self, verify_token):
        user = User.objects.create_user(
            username="existing-user",
            email=self.identity["email"],
            password="safe-test-password",
        )
        verify_token.return_value = self.identity

        response = self.client.post(self.url, {"id_token": "google-id-token"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["created"])
        user.refresh_from_db()
        self.assertEqual(user.google_subject, self.identity["subject"])
        self.assertTrue(user.has_usable_password())

    def test_rejects_missing_id_token(self):
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, 400)


class RoleDeterminationTests(TestCase):
    """Role must come strictly from TeamRoleAssignment: Admin/Booking Manager
    only when explicitly assigned, Client (None) otherwise — and it must
    never be auto-claimed on login or by merely loading an endpoint."""

    def _make_user(self, email, is_superuser=False):
        return User.objects.create_user(
            username=email.split("@")[0],
            email=email,
            password="test-pass-12345",
            is_superuser=is_superuser,
        )

    def test_admin_role_detection(self):
        admin_user = self._make_user("admin@example.com")
        TeamRoleAssignment.objects.create(role_name="Admin", assigned_user=admin_user)
        self.assertEqual(get_user_role(admin_user), "Admin")

    def test_booking_manager_role_detection(self):
        bm_user = self._make_user("bm@example.com")
        TeamRoleAssignment.objects.create(role_name="Booking Manager", assigned_user=bm_user)
        self.assertEqual(get_user_role(bm_user), "Booking Manager")

    def test_unassigned_user_is_client(self):
        plain_user = self._make_user("client@example.com")
        self.assertIsNone(get_user_role(plain_user))

    def test_login_never_auto_assigns_admin_seat_even_for_superuser(self):
        # Admin seat exists but is unassigned (e.g. freshly bootstrapped).
        TeamRoleAssignment.objects.create(role_name="Admin", assigned_user=None)
        superuser = self._make_user("super@example.com", is_superuser=True)

        _provision_client_if_unstaffed(superuser)

        admin_seat = TeamRoleAssignment.objects.get(role_name="Admin")
        self.assertIsNone(admin_seat.assigned_user)
        self.assertIsNone(get_user_role(superuser))
        self.assertTrue(Client.objects.filter(email__iexact=superuser.email).exists())

    def test_loading_team_roles_never_auto_assigns_admin_seat(self):
        TeamRoleAssignment.objects.create(role_name="Admin", assigned_user=None)
        bm_user = self._make_user("bm2@example.com")
        TeamRoleAssignment.objects.create(role_name="Booking Manager", assigned_user=bm_user)

        api_client = APIClient()
        api_client.force_authenticate(user=bm_user)
        response = api_client.get("/api/accounts/team-roles/")

        self.assertEqual(response.status_code, 200)
        admin_seat = TeamRoleAssignment.objects.get(role_name="Admin")
        self.assertIsNone(admin_seat.assigned_user)


class EnsureAdminSeatCommandTests(TestCase):
    """Safety guarantees of the `ensure_admin_seat` management command: it
    must never displace an existing Admin, and never touch anything but the
    Admin row."""

    def _make_user(self, email):
        return User.objects.create_user(username=email.split("@")[0], email=email, password="test-pass-12345")

    def test_fix_assigns_unassigned_seat_to_admin_email(self):
        TeamRoleAssignment.objects.create(role_name="Admin", assigned_user=None)
        admin_user = self._make_user(ADMIN_EMAIL)

        call_command("ensure_admin_seat", "--fix", stdout=StringIO())

        admin_seat = TeamRoleAssignment.objects.get(role_name="Admin")
        self.assertEqual(admin_seat.assigned_user_id, admin_user.id)

    def test_fix_refuses_to_displace_a_different_admin(self):
        someone_else = self._make_user("someone-else@example.com")
        TeamRoleAssignment.objects.create(role_name="Admin", assigned_user=someone_else)
        self._make_user(ADMIN_EMAIL)

        with self.assertRaises(CommandError):
            call_command("ensure_admin_seat", "--fix", stdout=StringIO())

        admin_seat = TeamRoleAssignment.objects.get(role_name="Admin")
        self.assertEqual(admin_seat.assigned_user_id, someone_else.id)

    def test_fix_leaves_booking_manager_rows_untouched(self):
        TeamRoleAssignment.objects.create(role_name="Admin", assigned_user=None)
        self._make_user(ADMIN_EMAIL)
        bm_user = self._make_user("bm3@example.com")
        TeamRoleAssignment.objects.create(role_name="Booking Manager", assigned_user=bm_user)

        call_command("ensure_admin_seat", "--fix", stdout=StringIO())

        bm_seat = TeamRoleAssignment.objects.get(role_name="Booking Manager")
        self.assertEqual(bm_seat.assigned_user_id, bm_user.id)

    def test_report_mode_never_mutates(self):
        TeamRoleAssignment.objects.create(role_name="Admin", assigned_user=None)
        self._make_user(ADMIN_EMAIL)

        call_command("ensure_admin_seat", stdout=StringIO())

        admin_seat = TeamRoleAssignment.objects.get(role_name="Admin")
        self.assertIsNone(admin_seat.assigned_user)


def _make_staff(email, role="Booking Manager", password="test-pass-12345"):
    user = User.objects.create_user(username=email.split("@")[0], email=email, password=password)
    TeamRoleAssignment.objects.create(role_name=role, assigned_user=user)
    return user


class MFAEnrollmentTests(TestCase):
    """F-2: enrollment (setup -> confirm) and its guardrails."""

    def setUp(self):
        self.staff = _make_staff("mfastaff@example.com")
        self.api_client = APIClient()
        self.api_client.force_authenticate(user=self.staff)

    def test_setup_issues_a_pending_device(self):
        response = self.api_client.post("/api/accounts/mfa/setup/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("secret", response.data)
        self.assertIn("otpauth_uri", response.data)
        device = TOTPDevice.objects.get(user=self.staff)
        self.assertFalse(device.confirmed)
        self.assertEqual(device.secret, response.data["secret"])

    def test_confirm_with_wrong_code_fails_and_leaves_device_unconfirmed(self):
        self.api_client.post("/api/accounts/mfa/setup/")
        response = self.api_client.post("/api/accounts/mfa/confirm/", {"code": "000000"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(TOTPDevice.objects.get(user=self.staff).confirmed)

    def test_confirm_with_correct_code_enables_mfa_and_issues_recovery_codes(self):
        setup_response = self.api_client.post("/api/accounts/mfa/setup/")
        secret = setup_response.data["secret"]
        code = pyotp.TOTP(secret).now()

        response = self.api_client.post("/api/accounts/mfa/confirm/", {"code": code}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.data["recovery_codes"]), 8)

        device = TOTPDevice.objects.get(user=self.staff)
        self.assertTrue(device.confirmed)
        self.assertEqual(device.recovery_codes.count(), 8)
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.MFA_ENABLED).exists())

    def test_confirm_twice_is_rejected(self):
        setup_response = self.api_client.post("/api/accounts/mfa/setup/")
        code = pyotp.TOTP(setup_response.data["secret"]).now()
        self.api_client.post("/api/accounts/mfa/confirm/", {"code": code}, format="json")

        response = self.api_client.post("/api/accounts/mfa/confirm/", {"code": code}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_status_reflects_enrollment(self):
        response = self.api_client.get("/api/accounts/mfa/status/")
        self.assertEqual(response.data, {"enabled": False})

        setup_response = self.api_client.post("/api/accounts/mfa/setup/")
        code = pyotp.TOTP(setup_response.data["secret"]).now()
        self.api_client.post("/api/accounts/mfa/confirm/", {"code": code}, format="json")

        response = self.api_client.get("/api/accounts/mfa/status/")
        self.assertEqual(response.data, {"enabled": True})

    def test_clients_cannot_reach_mfa_endpoints(self):
        client_user = User.objects.create_user(
            username="plainclient2", email="plainclient2@example.com", password="test-pass-12345"
        )
        api_client = APIClient()
        api_client.force_authenticate(user=client_user)
        response = api_client.post("/api/accounts/mfa/setup/")
        self.assertEqual(response.status_code, 403)


class MFALoginFlowTests(TestCase):
    """F-2: the password-login endpoint enforces MFA once a staff member
    has a confirmed device, and never for staff without one or for Clients."""

    def setUp(self):
        # H-5's login throttle counts against a shared cache that persists
        # across tests (unlike the DB, the cache isn't transactionally
        # rolled back) — clear it so one test's login attempts don't push
        # another test over the 5/min scope and 429 it.
        cache.clear()
        self.staff = _make_staff("mfalogin@example.com")
        self.api_client = APIClient()

    def _enroll(self, user):
        from django.contrib.auth.hashers import make_password

        secret = pyotp.random_base32()
        device = TOTPDevice.objects.create(user=user, secret=secret, confirmed=True)
        raw_code = "recoverycode123"
        device.recovery_codes.create(code_hash=make_password(raw_code))
        return device, raw_code

    def test_staff_without_mfa_logs_in_normally(self):
        response = self.api_client.post(
            "/api/accounts/login/", {"username": self.staff.username, "password": "test-pass-12345"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)

    def test_staff_with_mfa_is_blocked_without_a_code(self):
        self._enroll(self.staff)
        response = self.api_client.post(
            "/api/accounts/login/", {"username": self.staff.username, "password": "test-pass-12345"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("mfa_required", response.data)
        self.assertNotIn("access", response.data)

    def test_staff_with_mfa_logs_in_with_correct_totp_code(self):
        device, _raw_recovery = self._enroll(self.staff)
        code = pyotp.TOTP(device.secret).now()
        response = self.api_client.post(
            "/api/accounts/login/",
            {"username": self.staff.username, "password": "test-pass-12345", "totp_code": code},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)

    def test_staff_with_mfa_rejects_wrong_totp_code(self):
        self._enroll(self.staff)
        response = self.api_client.post(
            "/api/accounts/login/",
            {"username": self.staff.username, "password": "test-pass-12345", "totp_code": "000000"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("mfa_required", response.data)

    def test_recovery_code_works_once_then_is_rejected(self):
        _device, raw_code = self._enroll(self.staff)

        response = self.api_client.post(
            "/api/accounts/login/",
            {"username": self.staff.username, "password": "test-pass-12345", "recovery_code": raw_code},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        response = self.api_client.post(
            "/api/accounts/login/",
            {"username": self.staff.username, "password": "test-pass-12345", "recovery_code": raw_code},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_clients_are_never_prompted_for_mfa(self):
        client_user = User.objects.create_user(
            username="mfaclient", email="mfaclient@example.com", password="test-pass-12345"
        )
        response = self.api_client.post(
            "/api/accounts/login/", {"username": client_user.username, "password": "test-pass-12345"}, format="json"
        )
        self.assertEqual(response.status_code, 200)


class LogoutViewTests(TestCase):
    """M-1: logout actually blacklists the refresh token server-side."""

    def test_logout_blacklists_the_refresh_token(self):
        user = User.objects.create_user(
            username="logoutuser", email="logoutuser@example.com", password="test-pass-12345"
        )
        refresh = RefreshToken.for_user(user)

        api_client = APIClient()
        api_client.force_authenticate(user=user)
        response = api_client.post("/api/accounts/logout/", {"refresh": str(refresh)}, format="json")
        self.assertEqual(response.status_code, 205)

        # A blacklisted refresh token must no longer work.
        api_client.force_authenticate(user=None)
        refresh_response = api_client.post("/api/accounts/token/refresh/", {"refresh": str(refresh)}, format="json")
        self.assertEqual(refresh_response.status_code, 401)

    def test_logout_without_a_refresh_token_still_succeeds(self):
        user = User.objects.create_user(
            username="logoutuser2", email="logoutuser2@example.com", password="test-pass-12345"
        )
        api_client = APIClient()
        api_client.force_authenticate(user=user)
        response = api_client.post("/api/accounts/logout/", {}, format="json")
        self.assertEqual(response.status_code, 205)


class TransferAdminSeatCommandTests(TestCase):
    """F-4: the break-glass Admin-transfer command."""

    def test_dry_run_previews_without_changing_anything(self):
        admin_row = TeamRoleAssignment.objects.create(role_name="Admin", assigned_user=None)
        target = User.objects.create_user(username="newadmin", email="newadmin@example.com", password="test-pass-12345")

        call_command("transfer_admin_seat", "--to", target.email, stdout=StringIO())

        admin_row.refresh_from_db()
        self.assertIsNone(admin_row.assigned_user)

    def test_confirm_transfers_and_writes_an_audit_entry(self):
        current_admin = User.objects.create_user(
            username="oldadmin", email="oldadmin@example.com", password="test-pass-12345"
        )
        admin_row = TeamRoleAssignment.objects.create(role_name="Admin", assigned_user=current_admin)
        target = User.objects.create_user(
            username="newadmin2", email="newadmin2@example.com", password="test-pass-12345"
        )

        call_command("transfer_admin_seat", "--to", target.email, "--confirm", stdout=StringIO())

        admin_row.refresh_from_db()
        self.assertEqual(admin_row.assigned_user_id, target.id)
        entry = AuditLog.objects.get(action=AuditLog.Action.ADMIN_SEAT_TRANSFERRED)
        self.assertEqual(entry.changes["transferred_from"], current_admin.email)
        self.assertEqual(entry.changes["transferred_to"], target.email)

    def test_refuses_a_nonexistent_target(self):
        with self.assertRaises(CommandError):
            call_command("transfer_admin_seat", "--to", "nobody@example.com", "--confirm", stdout=StringIO())


class PwnedPasswordValidatorTests(TestCase):
    """F-3: breach screening — mocked throughout, so the test suite never
    depends on real network access to the HIBP API."""

    @patch("accounts.validators.requests.get")
    def test_rejects_a_password_found_in_the_range_response(self, mock_get):
        import hashlib

        from django.core.exceptions import ValidationError

        from .validators import PwnedPasswordValidator

        password = "definitely-pwned-password"
        suffix = hashlib.sha1(password.encode()).hexdigest().upper()[5:]
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.text = f"{suffix}:12345\nAAAAA0000000000000000000000000000:1"

        with self.assertRaises(ValidationError):
            PwnedPasswordValidator().validate(password)

    @patch("accounts.validators.requests.get")
    def test_accepts_a_password_not_in_the_range_response(self, mock_get):
        from .validators import PwnedPasswordValidator

        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.text = "AAAAA0000000000000000000000000000:1\nBBBBB1111111111111111111111111111:2"
        PwnedPasswordValidator().validate("some-password-not-in-the-list")  # must not raise

    def test_fails_open_when_the_api_is_unavailable(self):
        import requests

        from .validators import PwnedPasswordValidator

        with patch("accounts.validators.requests.get", side_effect=requests.RequestException("boom")):
            PwnedPasswordValidator().validate("any-password-at-all")  # must not raise


class OtpRequestPurposeTests(TestCase):
    """Login page vs Signup page (AuthScreen.js) now send a distinct
    `purpose`, which otp/request enforces. Asserts on the EmailOTP row
    (a synchronous DB write) rather than mail.outbox, since the actual
    send now happens on a background thread."""

    def setUp(self):
        self.api_client = APIClient()

    def test_signup_sends_an_otp_for_a_brand_new_email(self):
        response = self.api_client.post(
            "/api/accounts/otp/request/", {"email": "newclient@example.com", "purpose": "signup"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(EmailOTP.objects.filter(email="newclient@example.com").exists())

    def test_omitting_purpose_defaults_to_signup(self):
        response = self.api_client.post(
            "/api/accounts/otp/request/", {"email": "nopurpose@example.com"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(EmailOTP.objects.filter(email="nopurpose@example.com").exists())

    def test_login_sends_an_otp_for_an_existing_account(self):
        User.objects.create_user(username="existing", email="existing@example.com", password="test-pass-12345")
        response = self.api_client.post(
            "/api/accounts/otp/request/", {"email": "existing@example.com", "purpose": "login"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(EmailOTP.objects.filter(email="existing@example.com").exists())

    def test_login_rejects_an_unregistered_email_without_sending_an_otp(self):
        mail.outbox = []
        response = self.api_client.post(
            "/api/accounts/otp/request/", {"email": "ghost@example.com", "purpose": "login"}, format="json"
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("No account exists", response.data["detail"])
        self.assertFalse(EmailOTP.objects.filter(email="ghost@example.com").exists())
        # No admin/security alert either — nothing async was ever triggered.
        self.assertEqual(len(mail.outbox), 0)

    def test_login_rejection_is_case_insensitive_on_email(self):
        User.objects.create_user(username="mixedcase", email="MixedCase@Example.com", password="test-pass-12345")
        response = self.api_client.post(
            "/api/accounts/otp/request/", {"email": "mixedcase@example.com", "purpose": "login"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
