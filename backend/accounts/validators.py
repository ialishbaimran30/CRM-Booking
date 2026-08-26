"""Custom password validators (SecurityFeatures.md F-3)."""
import hashlib
import logging

import requests
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

HIBP_RANGE_URL = "https://api.pwnedpasswords.com/range/{prefix}"


class PwnedPasswordValidator:
    """Rejects passwords that appear in the Have I Been Pwned breach
    corpus (ASVS 6.2.12), using the k-anonymity range API — only the first
    5 characters of the password's SHA-1 hash are ever sent over the
    network, so the full password never leaves this process.

    Deliberately fails open on network/API errors: a third-party outage
    must not block every password change in the app. The failure is
    logged (not silent) so it's visible that the check didn't run.
    """

    def validate(self, password, user=None):
        sha1 = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
        prefix, suffix = sha1[:5], sha1[5:]

        try:
            response = requests.get(HIBP_RANGE_URL.format(prefix=prefix), timeout=3)
            response.raise_for_status()
        except requests.RequestException:
            logger.warning("Pwned Passwords API unavailable; skipping breach check for this password change.")
            return

        for line in response.text.splitlines():
            candidate_suffix, _count = line.split(":")
            if candidate_suffix == suffix:
                raise ValidationError(
                    _("This password has appeared in a public data breach. Please choose a different one."),
                    code="password_pwned",
                )

    def get_help_text(self):
        return _("Your password can't be one that has appeared in a known data breach.")
