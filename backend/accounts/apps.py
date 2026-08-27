from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        # M-7: require MFA at Django's own /admin/ login too, for any
        # account that has enrolled it — see accounts/admin_forms.py.
        from django.contrib import admin

        from .admin_forms import MFAAdminAuthenticationForm

        admin.site.login_form = MFAAdminAuthenticationForm
