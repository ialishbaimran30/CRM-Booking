"""Google identity verification and account-linking logic."""
import logging

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.validators import validate_email
from django.db import transaction
from django.utils.text import slugify
from google.auth import exceptions as google_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from .models import User

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
