from io import StringIO
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from clients.models import Client

from .management.commands.ensure_admin_seat import ADMIN_EMAIL
from .models import TeamRoleAssignment, User
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
