from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from .crypto import decrypt_token, encrypt_token
from .models import GoogleCalendarCredential

_KEY_A = "ZTWgMGeUPRAayCwzPduwuemG0x77zz9DTzkT8ZFdoRQ="
_KEY_B = "YjW54f62NV4teTw6vdbCobGSAwji7o_N_hdkleo5huo="


@override_settings(CALENDAR_TOKEN_KEYS=[_KEY_A])
class CalendarCryptoTests(TestCase):
    """M-2: the Calendar refresh-token key is now independent of
    SECRET_KEY, with MultiFernet-based rotation support."""

    def test_round_trips(self):
        encrypted = encrypt_token("raw-refresh-token")
        self.assertEqual(decrypt_token(encrypted), "raw-refresh-token")

    def test_decryption_fails_gracefully_with_a_key_it_wasnt_encrypted_under(self):
        encrypted = encrypt_token("raw-refresh-token")
        with override_settings(CALENDAR_TOKEN_KEYS=[_KEY_B]):
            self.assertIsNone(decrypt_token(encrypted))

    def test_rotate_calendar_key_command_re_encrypts_onto_the_new_key(self):
        credential = GoogleCalendarCredential.objects.create(refresh_token_encrypted=encrypt_token("old-token"))

        # Rotation step: new key first, old key still listed so decryption
        # of the existing row still works during the transition.
        with override_settings(CALENDAR_TOKEN_KEYS=[_KEY_B, _KEY_A]):
            call_command("rotate_calendar_key", stdout=StringIO())
            credential.refresh_from_db()
            self.assertEqual(decrypt_token(credential.refresh_token_encrypted), "old-token")

        # Final step: old key dropped entirely — must still decrypt, proving
        # the row was actually re-encrypted onto the new key, not just read.
        with override_settings(CALENDAR_TOKEN_KEYS=[_KEY_B]):
            self.assertEqual(decrypt_token(credential.refresh_token_encrypted), "old-token")

    def test_rotate_calendar_key_command_is_a_no_op_with_no_credential_row(self):
        call_command("rotate_calendar_key", stdout=StringIO())  # must not raise
        self.assertEqual(GoogleCalendarCredential.objects.count(), 0)
