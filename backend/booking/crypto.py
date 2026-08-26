"""Symmetric encryption for the Google Calendar refresh token at rest.

M-2 fix: the key used to live only as sha256(DJANGO_SECRET_KEY), which
welded its lifecycle to session/JWT signing — rotating one meant rotating
both, so in practice neither ever got rotated, and if SECRET_KEY was ever
the H-2 default, the Calendar key was trivially derivable too. The key now
has its own setting (CALENDAR_TOKEN_KEYS) and its own lifecycle.

Uses MultiFernet so rotation is possible without downtime: the first key
in the list encrypts; every key in the list can still decrypt. To rotate,
prepend a newly generated key, deploy, then run
`manage.py rotate_calendar_key` to re-encrypt the stored credential onto
it, then remove the old key on the next deploy.
"""
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _fernet():
    keys = getattr(settings, "CALENDAR_TOKEN_KEYS", None)
    if not keys:
        raise ImproperlyConfigured(
            "CALENDAR_TOKEN_KEY must be set to a Fernet key (generate one with "
            "`python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"`)."
        )
    return MultiFernet([Fernet(key.encode()) for key in keys])


def encrypt_token(raw_token):
    return _fernet().encrypt(raw_token.encode()).decode()


def decrypt_token(encrypted_token):
    try:
        return _fernet().decrypt(encrypted_token.encode()).decode()
    except InvalidToken:
        return None
