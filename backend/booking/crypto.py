"""Symmetric encryption for the Google Calendar refresh token at rest.

Key is derived deterministically from DJANGO_SECRET_KEY so no extra
required env var is needed, matching this project's existing minimal-config
style — the refresh token is still never stored in plaintext.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet():
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


def encrypt_token(raw_token):
    return _fernet().encrypt(raw_token.encode()).decode()


def decrypt_token(encrypted_token):
    try:
        return _fernet().decrypt(encrypted_token.encode()).decode()
    except InvalidToken:
        return None
