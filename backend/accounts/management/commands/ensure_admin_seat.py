"""Inspect (and, only with --fix, correct) the single Admin seat.

Read-only by default — prints every TeamRoleAssignment row so you can review
production role data before changing anything. With --fix, it will ONLY ever
assign the Admin seat to ADMIN_EMAIL, and ONLY when that seat is currently
unassigned; it refuses (no changes made) if Admin is already held by someone
else, and never touches any Booking Manager row or any other user.
"""
from django.core.management.base import BaseCommand, CommandError

from accounts.models import TeamRoleAssignment, User

ADMIN_EMAIL = "alishba.im13@gmail.com"


class Command(BaseCommand):
    help = "Report TeamRoleAssignment rows; with --fix, assign the Admin seat to alishba.im13 only if it is currently unassigned."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix",
            action="store_true",
            help=f"Assign the Admin seat to {ADMIN_EMAIL} if (and only if) it is currently unassigned.",
        )

    def handle(self, *args, **options):
        assignments = TeamRoleAssignment.objects.select_related("assigned_user").order_by("role_name", "id")

        self.stdout.write("Current TeamRoleAssignment rows:")
        if not assignments:
            self.stdout.write("  (none)")
        for row in assignments:
            who = row.assigned_user.email if row.assigned_user else "UNASSIGNED"
            self.stdout.write(f"  [{row.pk}] {row.role_name} -> {who}")

        admin_row = assignments.filter(role_name="Admin").first()

        if not options["fix"]:
            if admin_row and admin_row.assigned_user and admin_row.assigned_user.email.lower() == ADMIN_EMAIL:
                self.stdout.write(self.style.SUCCESS(f"\nAdmin seat is correctly held by {ADMIN_EMAIL}."))
            elif admin_row and admin_row.assigned_user:
                self.stdout.write(
                    self.style.WARNING(
                        f"\nAdmin seat is held by {admin_row.assigned_user.email}, not {ADMIN_EMAIL}. "
                        "Re-run with --fix only after confirming this is unintended."
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"\nAdmin seat is unassigned. Re-run with --fix to assign it to {ADMIN_EMAIL}.")
                )
            return

        if admin_row and admin_row.assigned_user:
            if admin_row.assigned_user.email.lower() == ADMIN_EMAIL:
                self.stdout.write(self.style.SUCCESS(f"No change needed - Admin seat already held by {ADMIN_EMAIL}."))
                return
            raise CommandError(
                f"Refusing to change anything: Admin seat is already held by "
                f"{admin_row.assigned_user.email}, not {ADMIN_EMAIL}. Resolve this manually — "
                "this command never displaces an existing Admin assignment."
            )

        try:
            target_user = User.objects.get(email__iexact=ADMIN_EMAIL)
        except User.DoesNotExist as exc:
            raise CommandError(f"No user with email {ADMIN_EMAIL} exists yet — nothing to assign.") from exc

        admin_row, _ = TeamRoleAssignment.objects.get_or_create(role_name="Admin")
        admin_row.assigned_user = target_user
        admin_row.save(update_fields=["assigned_user"])
        self.stdout.write(self.style.SUCCESS(f"Admin seat assigned to {ADMIN_EMAIL}."))
