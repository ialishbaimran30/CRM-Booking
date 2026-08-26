"""F-4: audited, explicit Admin-seat transfer for break-glass recovery.

Requires server/shell access to run — management commands aren't reachable
over HTTP — which is the intended authorization gate, the same shape as
_provision_client_if_unstaffed's existing superuser-claim precedent
elsewhere in this app (see accounts/views.py). Always writes an AuditLog
entry so a break-glass transfer is never a silent one. See
backend/ADMIN_RECOVERY.md for the full recovery procedure this supports.

Unlike ensure_admin_seat (a narrow, single-hardcoded-email fixup tool),
this command transfers the seat to any user and will move it even if
someone else currently holds it — that IS the point of a transfer command,
gated by requiring --confirm after a dry-run preview.
"""
from django.core.management.base import BaseCommand, CommandError

from accounts.models import TeamRoleAssignment, User
from core.audit import record_audit_event
from core.models import AuditLog


class Command(BaseCommand):
    help = "Transfer the single Admin seat to a different user. Requires server access; always audited."

    def add_arguments(self, parser):
        parser.add_argument("--to", required=True, help="Email of the user to assign the Admin seat to.")
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Actually perform the transfer. Omit to preview what would happen.",
        )

    def handle(self, *args, **options):
        target_email = options["to"]
        try:
            target_user = User.objects.get(email__iexact=target_email)
        except User.DoesNotExist as exc:
            raise CommandError(f"No user with email {target_email} exists — nothing to assign.") from exc

        admin_row, _created = TeamRoleAssignment.objects.get_or_create(role_name="Admin")
        previous_email = admin_row.assigned_user.email if admin_row.assigned_user else None

        if admin_row.assigned_user_id == target_user.id:
            self.stdout.write(self.style.SUCCESS(f"No change needed — {target_email} already holds the Admin seat."))
            return

        self.stdout.write(f"Admin seat is currently: {previous_email or 'UNASSIGNED'}")
        self.stdout.write(f"Would transfer to: {target_email}")

        if not options["confirm"]:
            self.stdout.write(self.style.WARNING("Preview only — re-run with --confirm to actually transfer."))
            return

        admin_row.assigned_user = target_user
        admin_row.save(update_fields=["assigned_user"])

        record_audit_event(
            actor=None,
            action=AuditLog.Action.ADMIN_SEAT_TRANSFERRED,
            target=admin_row,
            changes={
                "role_name": "Admin",
                "transferred_from": previous_email,
                "transferred_to": target_email,
                "via": "transfer_admin_seat management command (break-glass, F-4)",
            },
        )
        self.stdout.write(self.style.SUCCESS(f"Admin seat transferred to {target_email}."))
