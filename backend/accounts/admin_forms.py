"""M-7: extends Django's own admin-site login to require MFA for any
account that has enrolled it via the CRM's own /mfa/setup/ + /confirm/
flow (accounts/mfa.py) — the same TOTPDevice, not a second, separate MFA
system. Closes the gap where F-2's MFA only guarded the CRM's own
POST /api/accounts/login/, leaving Django's built-in /admin/ site
(reachable by anyone with is_superuser=True, and just as capable of full
administrative access via raw model views) with no second factor at all.
"""
from django import forms
from django.contrib.admin.forms import AdminAuthenticationForm
from django.utils.translation import gettext_lazy as _

from core.audit import log_security_event

from .mfa import get_confirmed_device, verify_login_mfa


class MFAAdminAuthenticationForm(AdminAuthenticationForm):
    totp_code = forms.CharField(
        label=_("Authentication code"),
        required=False,
        strip=True,
        help_text=_(
            "Only required if you have MFA enabled on your account. "
            "Enter a code from your authenticator app, or a recovery code."
        ),
    )

    def clean(self):
        cleaned_data = super().clean()
        user = getattr(self, "user_cache", None)
        if user is not None:
            device = get_confirmed_device(user)
            if device:
                code = (cleaned_data.get("totp_code") or "").strip()
                ok, _used_recovery = verify_login_mfa(device, code, code)
                if not ok:
                    self.user_cache = None
                    log_security_event(
                        "admin_site_login", self.request, outcome="mfa_required_or_invalid", actor=user,
                    )
                    raise forms.ValidationError(
                        _("Enter a valid authentication code from your authenticator app, or a recovery code."),
                        code="mfa_required",
                    )
                log_security_event("admin_site_login", self.request, outcome="success", actor=user)
        return cleaned_data
