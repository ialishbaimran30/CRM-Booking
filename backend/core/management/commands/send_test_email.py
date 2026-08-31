"""Send one real email through the configured EMAIL_BACKEND to prove the
SMTP transport (Brevo) actually accepts mail from this deployment.

Every application email path -- OTP (accounts/services.py), booking
confirm/reschedule/cancel/update + waitlist (booking/emails.py), generic
notifications (notifications/services.py) and security alerts
(core/alerting.py via mail_admins) -- goes through this same backend and
these same EMAIL_* settings, so a success here means all of them can send.

Usage:
    python manage.py send_test_email --to you@example.com
    python manage.py send_test_email --to you@example.com --admins

--admins additionally exercises the mail_admins() path used by
core/alerting.py, sending from SERVER_EMAIL to settings.ADMINS.

This does NOT touch OTP generation, templates, business logic, or Google
Calendar -- it only opens an SMTP conversation and reports exactly what the
server said.
"""
import smtplib

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection, mail_admins
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Send a test email through the configured SMTP backend (Brevo) and report the result."

    def add_arguments(self, parser):
        parser.add_argument("--to", required=True, help="Recipient address for the test message.")
        parser.add_argument(
            "--admins", action="store_true",
            help="Also send via mail_admins() (SERVER_EMAIL -> settings.ADMINS), the security-alert path.",
        )

    def handle(self, *args, **options):
        recipient = options["to"]

        self.stdout.write("Resolved email configuration:")
        for key in ("EMAIL_BACKEND", "EMAIL_HOST", "EMAIL_PORT", "EMAIL_USE_TLS",
                    "EMAIL_USE_SSL", "EMAIL_TIMEOUT", "EMAIL_HOST_USER",
                    "DEFAULT_FROM_EMAIL", "EMAIL_REPLY_TO", "SERVER_EMAIL"):
            self.stdout.write(f"  {key} = {getattr(settings, key, None)!r}")
        pw = getattr(settings, "EMAIL_HOST_PASSWORD", "") or ""
        if not pw:
            pw_desc = "<empty>"
        elif pw.startswith("xsmtpsib-"):
            pw_desc = f"<set, {len(pw)} chars, looks like a Brevo SMTP key>"
        else:
            pw_desc = f"<set, {len(pw)} chars, NOT an xsmtpsib- key>"
        self.stdout.write(f"  EMAIL_HOST_PASSWORD = {pw_desc}")

        try:
            connection = get_connection()
            message = EmailMultiAlternatives(
                subject="CRM & Booking - SMTP test",
                body="Plain-text test body. If you received this, the Brevo SMTP transport works.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[recipient],
                reply_to=[settings.EMAIL_REPLY_TO] if getattr(settings, "EMAIL_REPLY_TO", None) else None,
                connection=connection,
            )
            message.attach_alternative(
                "<p>HTML test body. If you received this, the Brevo SMTP transport works.</p>",
                "text/html",
            )
            sent = message.send(fail_silently=False)
        except smtplib.SMTPAuthenticationError as exc:
            raise CommandError(
                f"SMTP authentication failed ({exc.smtp_code} {exc.smtp_error!r}). "
                "EMAIL_HOST_USER must be the exact Login from Brevo -> SMTP & API -> SMTP, "
                "and EMAIL_HOST_PASSWORD the SMTP key (xsmtpsib-...) from that page -- not the "
                "account password or a v3 API key. Also confirm transactional sending is "
                "enabled on the Brevo account."
            )
        except smtplib.SMTPSenderRefused as exc:
            raise CommandError(
                f"Sender refused ({exc.smtp_code} {exc.smtp_error!r}). "
                f"DEFAULT_FROM_EMAIL ({settings.DEFAULT_FROM_EMAIL!r}) must be a Verified sender "
                "under Brevo -> Senders, Domains & Dedicated IPs."
            )
        except smtplib.SMTPRecipientsRefused as exc:
            raise CommandError(f"Recipient refused: {exc.recipients!r}")
        except Exception as exc:  # noqa: BLE001 - report whatever the backend raised
            raise CommandError(f"{type(exc).__name__}: {exc}")

        if not sent:
            raise CommandError("Backend reported 0 messages sent (no exception raised).")

        self.stdout.write(self.style.SUCCESS(f"OK - transactional test message accepted for {recipient}."))

        if options["admins"]:
            if not settings.ADMINS:
                self.stdout.write(self.style.WARNING(
                    "--admins skipped: settings.ADMINS is empty (set SECURITY_ALERT_EMAILS)."
                ))
            else:
                try:
                    mail_admins(
                        "CRM & Booking - SMTP test (admins)",
                        "If you received this, the security-alert mail path works.",
                        fail_silently=False,
                    )
                except Exception as exc:  # noqa: BLE001
                    raise CommandError(f"mail_admins() failed - {type(exc).__name__}: {exc}")
                self.stdout.write(self.style.SUCCESS(
                    f"OK - mail_admins() accepted for {[a[1] for a in settings.ADMINS]}."
                ))
