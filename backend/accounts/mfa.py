"""TOTP enrollment and verification service logic (SecurityFeatures.md F-2).

Kept separate from views.py/serializers.py so the login-flow integration
in LoggingTokenObtainPairSerializer stays a thin call into here rather
than growing MFA logic inline into the F-1 login-logging code it sits
next to.
"""
import secrets

import pyotp
from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone

from .models import TOTPDevice, TOTPRecoveryCode

RECOVERY_CODE_COUNT = 8
ISSUER_NAME = "CRM Booking"


def start_enrollment(user):
    """Create (or replace) a pending, unconfirmed device for this user and
    return its provisioning URI for the client to render as a QR code."""
    TOTPDevice.objects.filter(user=user).delete()
    secret = pyotp.random_base32()
    device = TOTPDevice.objects.create(user=user, secret=secret, confirmed=False)
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=ISSUER_NAME)
    return device, uri


def _generate_recovery_codes(device):
    """Generate RECOVERY_CODE_COUNT codes, store only their hashes, and
    return the raw codes — the only time they are ever available in the
    clear. Any prior codes for this device are invalidated."""
    device.recovery_codes.all().delete()
    raw_codes = [secrets.token_hex(5) for _ in range(RECOVERY_CODE_COUNT)]
    TOTPRecoveryCode.objects.bulk_create(
        [TOTPRecoveryCode(device=device, code_hash=make_password(code)) for code in raw_codes]
    )
    return raw_codes


def confirm_enrollment(device, totp_code):
    """Verify the first code from the authenticator app and, if correct,
    confirm the device and issue recovery codes. Returns the raw recovery
    codes on success, None on an incorrect code."""
    if not pyotp.TOTP(device.secret).verify(totp_code, valid_window=1):
        return None
    device.confirmed = True
    device.confirmed_at = timezone.now()
    device.save(update_fields=["confirmed", "confirmed_at"])
    return _generate_recovery_codes(device)


def get_confirmed_device(user):
    return TOTPDevice.objects.filter(user=user, confirmed=True).first()


def verify_login_mfa(device, totp_code, recovery_code):
    """Returns (ok, used_recovery_code). Tries the TOTP code first, then
    falls back to an unused recovery code."""
    if totp_code and pyotp.TOTP(device.secret).verify(totp_code, valid_window=1):
        return True, False

    if recovery_code:
        for candidate in device.recovery_codes.filter(used_at__isnull=True):
            if check_password(recovery_code, candidate.code_hash):
                candidate.used_at = timezone.now()
                candidate.save(update_fields=["used_at"])
                return True, True

    return False, False


def verify_reauth(user, existing_device, *, current_password="", totp_code="", recovery_code=""):
    """M-7: proves the caller still controls this account before a
    security-critical change (replacing an already-confirmed MFA device) —
    a valid session/access token alone must not be enough. Accepts any ONE
    of: the current password, a valid code from the device being replaced,
    or one of its recovery codes. Only called when a confirmed device
    already exists; first-time enrollment needs no such proof, since
    there's nothing prior to prove possession of."""
    if current_password and user.check_password(current_password):
        return True
    if totp_code or recovery_code:
        ok, _used_recovery = verify_login_mfa(existing_device, totp_code, recovery_code)
        if ok:
            return True
    return False
