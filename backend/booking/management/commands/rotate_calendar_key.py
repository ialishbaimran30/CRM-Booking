"""M-2: re-encrypt the stored Google Calendar refresh token onto the
current (first) CALENDAR_TOKEN_KEY.

Rotation procedure:
1. Generate a new key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
2. Set CALENDAR_TOKEN_KEY to "<new-key>,<old-key>" (new first) and deploy —
   decryption still works via the old key, nothing breaks.
3. Run this command. It re-encrypts the stored credential using the first
   (new) key.
4. Set CALENDAR_TOKEN_KEY to just "<new-key>" and deploy again.

Safe to run with no GoogleCalendarCredential row present (no-op).
"""
from django.core.management.base import BaseCommand

from booking.crypto import decrypt_token, encrypt_token
from booking.models import GoogleCalendarCredential


class Command(BaseCommand):
    help = "Re-encrypt the stored Google Calendar refresh token onto the current CALENDAR_TOKEN_KEY."

    def handle(self, *args, **options):
        credential = GoogleCalendarCredential.objects.first()
        if credential is None:
            self.stdout.write("No GoogleCalendarCredential row exists — nothing to rotate.")
            return

        raw_token = decrypt_token(credential.refresh_token_encrypted)
        if raw_token is None:
            self.stderr.write(self.style.ERROR(
                "Stored credential could not be decrypted with any configured key. "
                "Reconnect Calendar via /admin-tools/google-calendar/connect/ instead."
            ))
            return

        credential.refresh_token_encrypted = encrypt_token(raw_token)
        credential.save(update_fields=["refresh_token_encrypted"])
        self.stdout.write(self.style.SUCCESS("Calendar credential re-encrypted onto the current key."))
