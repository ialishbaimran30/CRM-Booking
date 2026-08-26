# Admin seat recovery (break-glass)

SecurityFeatures.md F-4. The CRM has exactly one Admin seat, enforced by a
database constraint (`accounts_single_admin_seat`). There is no in-app,
self-service way to become Admin — that's deliberate (see H-3 in
`.claude/memory/SecurityIssues.md`): a Booking Manager must never be able
to silently promote themselves by loading a page.

That means recovering the seat requires server access. This is the
official, audited procedure.

## When to use this

- The Admin's account was deleted or disabled (offboarding, compromise).
- The Admin lost access to their account (lost password, lost MFA device
  once F-2 ships) and no one else can assign roles.
- A fresh deployment has no Admin at all.

## Who is authorised

Whoever has shell/SSH access to the production container, or direct
Azure Portal access to run an App Service SSH session or a one-off
management command. That is the authorisation gate — the same one Django
admin superuser access already implies.

## Procedure

1. Confirm the target user already has an account (they must sign up via
   OTP or Google sign-in first if they don't — this command assigns the
   seat, it doesn't create the user).
2. From a shell with access to the backend container:
   ```
   python manage.py transfer_admin_seat --to <email>
   ```
   Run **without** `--confirm` first — this previews the current holder
   and the target without changing anything.
3. Once confirmed correct, run:
   ```
   python manage.py transfer_admin_seat --to <email> --confirm
   ```
4. This writes an `AuditLog` entry (`admin_seat_transferred`, `via:
   transfer_admin_seat management command (break-glass, F-4)`) — visible
   in Django admin under Audit logs. **This step is what makes the
   transfer accountable**; do not go around it by editing the database
   directly.
5. Notify the rest of the team the Admin seat changed hands and why.

## Notes

- `ensure_admin_seat` (an older, narrower command in this codebase) only
  ever assigns the seat to one hardcoded email and refuses to displace an
  existing Admin. It's a fixup tool for that one specific deployment
  concern, not a general recovery path — use `transfer_admin_seat` for
  break-glass recovery.
- There is deliberately no automatic seat-claiming on login, for anyone,
  superuser or not (see H-3). Do not reintroduce one.
