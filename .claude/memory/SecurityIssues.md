# SecurityIssues.md — CRM-Booking Vulnerability Audit

**Audit date:** 2026-08-25
**Auditor:** `security-auditor` agent, grounded in the `owasp-security` skill (OWASP Top 10:2025, ASVS 5.0)
**Lens:** *What is implemented, and wrong?* — the paired control-gap file is `.claude/memory/SecurityFeatures.md`.

---

## How to use this file

- **IDs are stable.** `H-3`, `M-1`, etc. are safe to reference in later conversations ("fix H-1 and H-5"). Never renumber them.
- **Mark, don't delete.** When an item is resolved, change `Status: OPEN` to `Status: FIXED 2026-09-01` and leave the entry in place. Use `Status: ACCEPTED RISK <reason>` when the team decides not to act. This file is a living tracker, not a snapshot.
- **Each CRITICAL/HIGH/MEDIUM entry is a standalone implementation brief.** You should be able to ship the fix from the entry alone without re-auditing the codebase. LOW/INFORMATIONAL are deliberately condensed.
- **Every entry carries a `Why (preserved reasoning)` line.** If the code has changed such that that reasoning no longer holds, the finding is stale — re-verify before acting.
- **A full re-audit is only warranted when the code has moved materially** (a payment gateway lands, a new app is added, the permission model changes). Fixing individual items does not require one.

### Architecture orientation (context every finding below assumes)

CRM-Booking is a **Django 5.2 / DRF backend** (`backend/`, nine apps: `accounts`, `clients`, `booking`, `resources`, `payments`, `dashboard`, `notifications`, `reports`, `core`) plus a **React 19 CRA frontend** (`frontend/src/`), deployed to Azure — the backend as a Docker container to App Service, the frontend to Azure Static Web Apps.

Authorization is **per-view, not centralized**. `REST_FRAMEWORK.DEFAULT_PERMISSION_CLASSES` is only `IsAuthenticated`, so *"logged in"* is the sole global gate; the client/staff/admin boundary is enforced by each viewset opting into `IsAdmin` / `IsStaffMember` / `IsAdminOrReadOnly` from `backend/accounts/permissions.py`. **A viewset that forgets to add one is fully open to any authenticated user** — that is the root cause of H-1, and it is the single most important structural fact about this codebase.

Access is **hybrid**: the client side is public self-serve (anyone can obtain an account via email OTP or Google Sign-In at `/api/accounts/otp/request/`, `/otp/verify/`, `/google/`), while the staff side is admin-provisioned (`TeamRoleAssignment` rows). **Role is derived, not stored on the user**: `get_user_role()` returns `'Admin'`, `'Booking Manager'`, or `None`, and `None` means "Client". So *any* self-registered stranger is an authenticated principal with a Client role — the bar for reaching an `IsAuthenticated`-only endpoint is "owns an email address".

Actors, highest privilege first: **Admin** (exactly one seat, DB-constrained) → **Booking Manager** (staff, many) → **Client** (authenticated, no role row) → **Anonymous**. Plus a **Google Calendar service** identity (server-to-server, encrypted refresh token) and outbound **SMTP**.

---

## Executive summary

**Production-readiness: NOT READY.** The codebase shows genuine, above-average security craftsmanship in its core flows — the OTP implementation, the booking write path, and the Google OAuth handshake are all correctly built (see *Areas already done well*). But five HIGH findings stand between it and production, and they are not exotic: one entire app (`resources`) ships with no authorization at all, exposing staff PII to any self-registered stranger; the password login endpoint has no rate limiting whatsoever; a Booking Manager can silently promote themselves to Admin; a Client can destroy financial records; and the app falls back to a publicly-known `SECRET_KEY` rather than refusing to boot.

No CRITICAL findings: nothing is exploitable by a fully unauthenticated attacker against the code *as configured*, with the one caveat that H-2 becomes an unauthenticated authentication bypass if `DJANGO_SECRET_KEY` is unset in the deployed environment — which is runtime-verifiable only (see *Areas needing manual testing*).

**Update 2026-08-25:** All 5 HIGH findings and M-5 are now FIXED or PARTIALLY FIXED — see each entry's `Status` line. H-5's fix is only partial pending `L-5` (shared cache). H-3's underlying auto-claim bug was already absent from the code when reviewed; only the deterministic-ordering hardening was newly applied.

**Update 2026-08-27:** All remaining MEDIUM findings are now FIXED or PARTIALLY FIXED — M-1, M-2, M-3, M-4 FIXED; M-6 PARTIALLY FIXED (exact version pins, not a full hash-verified lock file). Every HIGH and MEDIUM finding in this file now has a non-OPEN status. Remaining open work in this file is entirely LOW/INFORMATIONAL.

Injection (A05:2025) is effectively absent: no raw SQL, no shell execution, no deserialization, no `eval`, no `mark_safe` anywhere in the backend, and no `dangerouslySetInnerHTML` anywhere in the frontend.

| Severity | Count |
|---|---|
| CRITICAL | 0 |
| HIGH | 5 |
| MEDIUM | 6 |
| LOW | 7 |
| INFORMATIONAL / HARDENING | 6 |
| **Total** | **24** |

---

## Scan coverage

**Examined in full:** `backend/accounts/` (permissions, views, models, services, serializers, urls); `backend/bookings/` (settings.py, urls.py, asgi.py); `backend/booking/` (views, serializers, models, crypto.py, google_calendar.py, admin_calendar_views.py, emails.py); `backend/payments/` (views, serializers, services, pdf.py); `backend/clients/` (views, models); `backend/resources/` (views, models, serializers, urls); `backend/reports/` (views, services); `backend/dashboard/views.py`; `backend/notifications/` (views, consumers, middleware, routing); `backend/requirements.txt` + installed `.venv` versions; `backend/Dockerfile`, `.dockerignore`, `.gitignore`; both `.github/workflows/`; git history for committed secrets; `frontend/src/api/axiosInstance.js`, `hooks/useNotificationSocket.js`; targeted greps across all of `frontend/src/` for XSS sinks and `localStorage` use.

**Not examined (or only skimmed):** the bulk of `frontend/src/pages/` and `components/` beyond the grep sweeps for XSS sinks and token handling — UI-layer logic was not read line by line; `backend/*/migrations/` (read only for schema confirmation); `backend/booking/signals.py`, `slots.py`, `admin.py`, and `notifications/services.py` (read only insofar as call sites required); `backend/booking/templates/emails/` (confirmed Django autoescaping applies, individual templates not reviewed); `frontend/package.json` dependency tree beyond confirming `package-lock.json` exists.

**Not verifiable from code (runtime only):** actual deployed env-var values, real `ALLOWED_HOSTS` / `CORS_ALLOWED_ORIGINS` / `CSRF_TRUSTED_ORIGINS`, TLS configuration at the Azure edge, and the strength of the deployed `DJANGO_SECRET_KEY`. See *Areas needing manual testing*.

**Assessed and ruled not applicable:** LLM Top 10:2025 and Agentic AI ASI01–ASI10 — grep for `openai|anthropic|generativeai|langchain|mistralai|cohere|ollama` across the repo matched nothing but this auditor's own agent definition; there is no LLM, agent, or RAG component.

---

## FINDINGS

---

### HIGH

---

#### H-1 — `resources` app exposes staff PII and accepts writes from any authenticated Client
**Severity:** HIGH · **Class:** Broken Access Control
**OWASP:** A01:2025 · **ASVS 5.0:** 8.2.1 (function-level access), 8.2.2 (data-level access), 8.3.1 (trusted-layer enforcement)
**Status: FIXED 2026-08-25** — all three viewsets now require `IsStaffMember`; no frontend code called these routes, so the deny-by-default option was taken for `ResourceViewSet` too.

**Location**
- `backend/resources/views.py:12` — `class StaffViewSet(viewsets.ModelViewSet)` → `permission_classes = [IsAuthenticated]` (line 15)
- `backend/resources/views.py:23` — `class ResourceViewSet(viewsets.ModelViewSet)` → `permission_classes = [IsAuthenticated]` (line 26)
- `backend/resources/views.py:34` — `class BookingAssignmentViewSet(viewsets.ModelViewSet)` → `permission_classes = [IsAuthenticated]` (line 37)
- Routes registered at `backend/resources/urls.py:8-10` → `/api/resources/staff/`, `/api/resources/resources/`, `/api/resources/assignments/`
- `backend/resources/serializers.py:6-13` — `StaffSerializer` exposes `username` and `email` sourced from the related `User`

**Evidence.** All three are full `ModelViewSet`s (GET/POST/PUT/PATCH/DELETE) whose only permission class is `IsAuthenticated`. Unlike every other business module — `clients` and `payments` add `IsStaffMember`, `dashboard` and `reports` add `IsAdmin` — the `resources` app adds nothing. `StaffSerializer` declares:

```python
username = serializers.CharField(source="user.username", read_only=True)
email    = serializers.EmailField(source="user.email", read_only=True)
```

**Attack scenario.** An **Anonymous** attacker self-registers as a **Client** in two requests against the public, `AllowAny` OTP endpoints (`POST /api/accounts/otp/request/` then `/otp/verify/` with any email they control) — no staff approval is involved. With that ordinary Client JWT they then:
1. `GET /api/resources/staff/` → the full staff roster, every staff member's **username and email address**. This is a ready-made target list for the unthrottled password endpoint in **H-5**.
2. `DELETE /api/resources/assignments/{id}/` → destroys which staff member and which room is assigned to any booking, silently breaking operations.
3. `POST /api/resources/resources/` / `PATCH .../{id}/` → injects or renames rooms and equipment in the business's own catalog.
4. `DELETE /api/resources/staff/{id}/` → deletes the `Staff` profile row for a real staff member.

**Impact.** Mass disclosure of staff PII to anyone on the internet willing to register, plus unauthenticated-in-practice write and delete access to operational scheduling data. This is the highest-severity finding in the audit because the precondition — "hold a Client account" — is self-serve by design.

**Remediation.** Add the staff gate to all three viewsets, matching the pattern already used in `clients/views.py:24`. In `backend/resources/views.py`:

```python
# add to the existing imports
from accounts.permissions import IsStaffMember, IsAdminOrReadOnly

class StaffViewSet(viewsets.ModelViewSet):
    ...
    permission_classes = [IsAuthenticated, IsStaffMember]   # was: [IsAuthenticated]

class ResourceViewSet(viewsets.ModelViewSet):
    ...
    # Clients legitimately may need to *read* the room/equipment catalog to book;
    # if they do not, use [IsAuthenticated, IsStaffMember] instead.
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]

class BookingAssignmentViewSet(viewsets.ModelViewSet):
    ...
    permission_classes = [IsAuthenticated, IsStaffMember]
```

Decide deliberately whether Clients need read access to `Resource`; if the Client Portal never calls `/api/resources/resources/`, prefer `IsStaffMember` there too and keep the deny-by-default posture.

**Ripple effects.** Check `frontend/src/` for any Client-Portal component calling `/api/resources/...`; if the client-side booking flow reads the resource catalog, `ResourceViewSet` must keep `IsAdminOrReadOnly` (read-open) rather than `IsStaffMember`, or that screen will start 403-ing. No migration, no env var, no deploy variable. Consider whether `StaffSerializer` should expose `email` to Booking Managers at all, or only to Admin.

**Verification.** Obtain a Client JWT (register via OTP with a throwaway address, confirm `GET /api/accounts/team-roles/me/` returns `"role": null`). Then `GET /api/resources/staff/` with that token **must return 403**, not 200. Repeat for `POST /api/resources/resources/` and `DELETE /api/resources/assignments/1/`. Add a regression test in `backend/resources/tests.py` (currently a 1-line stub) asserting 403 for a role-less user on all three routes and 200 for a Booking Manager.

**Why (preserved reasoning).** Traced from the public `AllowAny` OTP registration path → role-less `User` → `IsAuthenticated` passes → `ModelViewSet` full CRUD, with no `get_queryset` filtering and no object-level check anywhere in `resources/`. Stale only if `permission_classes` on these three classes changes.

---

#### H-2 — `DJANGO_SECRET_KEY` falls back to a publicly-known default instead of failing closed
**Severity:** HIGH (becomes CRITICAL if the env var is unset in production) · **Class:** Security Misconfiguration / Cryptographic Failure
**OWASP:** A02:2025, A04:2025 · **ASVS 5.0:** 13.x (configuration), 11.4.1 (approved key material)
**Status: FIXED 2026-08-25** — `SECRET_KEY` now raises `ImproperlyConfigured` and refuses to boot when `DJANGO_DEBUG` is not true and `DJANGO_SECRET_KEY` is unset; verified with `manage.py check` in both states. Confirm the Azure App Setting is actually set before the next deploy.

**Location** — `backend/bookings/settings.py:22`

```python
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "change-this-before-production")
```

**Evidence.** The fallback string is committed to the repository and therefore public. `SIMPLE_JWT` (`settings.py:161-166`) does **not** set `SIGNING_KEY`, so SimpleJWT defaults to `settings.SECRET_KEY` with HS256. The same value is also the input to the Fernet key derivation in `backend/booking/crypto.py:15` (see **M-2**), and signs Django sessions and CSRF tokens.

**Attack scenario.** If the container is ever deployed without `DJANGO_SECRET_KEY` set — an ordinary Azure App Service misconfiguration, since the app boots and serves traffic perfectly well without it — an **Anonymous** remote attacker who knows this repository (or simply guesses this extremely common placeholder) can locally forge a valid HS256 JWT with an arbitrary `user_id` claim. That is a complete authentication bypass: they mint an Admin token, then read every client's PII via `/api/clients/`, every invoice via `/api/payments/`, and assign themselves roles. The same key also decrypts the stored Google Calendar refresh token.

**Impact.** Full authentication bypass and mass data exposure, gated only on a deployment variable being forgotten. The defect in the code is that it **fails open** — it prefers booting insecurely over refusing to boot.

**Remediation.** Fail closed. In `backend/bookings/settings.py`, replace line 22 with:

```python
from django.core.exceptions import ImproperlyConfigured

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if os.getenv("DJANGO_DEBUG", "false").lower() == "true":
        SECRET_KEY = "insecure-dev-only-key-do-not-use-in-production"
    else:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is not true."
        )
```

This keeps `runserver` frictionless for local development while making a production boot without the variable impossible. Generate the real value with `python -c "import secrets; print(secrets.token_urlsafe(64))"`.

**Ripple effects.** `DJANGO_SECRET_KEY` is already documented in `backend/.env.example`, so no change is needed there — but confirm it is actually set as an Azure App Service **Application Setting** for `crm-booking-backend` before merging this, or the next deploy will crash-loop (which is the intended fail-closed behaviour, but should be a planned event, not a surprise outage). Note the ordering constraint: `DEBUG` is currently read at line 23, *after* line 22 — the snippet above reads `DJANGO_DEBUG` directly from the environment to avoid a forward reference. Rotating this key invalidates all issued JWTs and sessions, and will render the stored Google Calendar credential undecryptable (see **M-2**) — reconnect Calendar afterwards via `/admin-tools/google-calendar/connect/`.

**Verification.** With `DJANGO_DEBUG=false` and `DJANGO_SECRET_KEY` unset, `python manage.py check` must raise `ImproperlyConfigured` and the process must refuse to start. With the variable set, it must start normally. Separately, confirm on the live deployment that `SECRET_KEY` is not the placeholder — see *Areas needing manual testing*.

**Why (preserved reasoning).** Traced `SECRET_KEY` → SimpleJWT default `SIGNING_KEY` → JWT forgery, and → `crypto.py:_fernet()` → Calendar token decryption. Stale only if `SIMPLE_JWT["SIGNING_KEY"]` is later set to an independent secret AND the fallback is removed.

---

#### H-3 — A Booking Manager can silently promote themselves to Admin by listing the team roster
**Severity:** HIGH · **Class:** Broken Access Control / Privilege Escalation
**OWASP:** A01:2025 · **ASVS 5.0:** 8.2.1, 8.3.1
**Status: FIXED (pre-existing) + hardened 2026-08-25** — `TeamManagementViewSet.get_queryset` no longer writes `assigned_user`; it only bootstraps the vacant Admin row, and the auto-claim this entry describes was already gone from the codebase by the time this was reviewed. Applied the remaining recommended hardening: `get_user_role` now uses `order_by("role_name")` so role resolution is deterministic if a user ever holds two rows. Note: `F-4` in `SecurityFeatures.md` (Admin break-glass recovery) is still open — there is currently no bootstrap path at all for a vacant Admin seat other than direct DB/Django-admin access.

**Location** — `backend/accounts/views.py:203-211`, `class TeamManagementViewSet` → `def get_queryset`

```python
def get_queryset(self):
    admin_role, _ = TeamRoleAssignment.objects.get_or_create(role_name='Admin')
    if not admin_role.assigned_user and self.request and self.request.user and self.request.user.is_authenticated:
        admin_role.assigned_user = self.request.user
        admin_role.save()
    return super().get_queryset()
```

Related: `backend/accounts/models.py:74-76` — `assigned_user = models.ForeignKey(User, on_delete=models.SET_NULL, ...)`; `backend/accounts/permissions.py:11` — `def get_user_role`.

**Evidence.** `get_queryset` performs a **write** — it claims the vacant Admin seat for whoever is making the request. It runs on `list` and `retrieve`, i.e. on a plain `GET`. The viewset's `permission_classes` (line 201) are `[IsAuthenticated, IsStaffMember, IsAdminOrReadOnly]`; `IsAdminOrReadOnly` permits **any** safe method, so a Booking Manager passes all three on a GET and reaches this code.

A Client cannot reach it — `IsStaffMember` requires a `TeamRoleAssignment` row and correctly blocks role-less users. **The escalation is Booking Manager → Admin, not Client → Admin.**

The Admin seat becomes vacant in three realistic ways: (1) the Admin's `User` row is deleted — `on_delete=SET_NULL` nulls `assigned_user` rather than removing the seat; (2) the Admin explicitly unassigns it (`TeamRoleSerializer.assigned_user_id` is `allow_null=True`); (3) on a fresh install `get_or_create` creates the row vacant and the very next line claims it.

**Attack scenario.** A **Booking Manager** — a real employee, deliberately given the lesser of the two staff roles — waits for or induces a vacant Admin seat (most plausibly: the Admin leaves the company and their account is deleted during offboarding). They then open the Team Management screen, which issues `GET /api/accounts/team-roles/`. No confirmation, no audit record, no UI affordance: they are now Admin, gaining `TeamManagementViewSet` write access (assign roles to anyone), invoice create/update/delete and refunds (`payments/views.py:82-88`), discount and coupon application, and the Admin-only `dashboard` and `reports` modules.

**One honest caveat on exploitability.** After the claim the user holds two rows (`Booking Manager` and `Admin`), and `get_user_role` (`permissions.py:11`) resolves with `.filter(assigned_user=user).first()` — **no `order_by`**, so which role wins is database-ordering-dependent. In the realistic sequence the Admin seat row is bootstrapped first and holds the lower primary key, so `.first()` returns `'Admin'` and the escalation lands. But this is undefined behaviour either way, and the ambiguity is itself a defect worth fixing alongside.

**Impact.** Vertical privilege escalation across the system's most important trust boundary, triggered by a read-shaped request, leaving no trace.

**Remediation.** Two changes, both required.

1. **Remove the write from `get_queryset`.** A queryset method must never mutate state. Replace lines 203-211 with:

```python
def get_queryset(self):
    return super().get_queryset()
```

Seat bootstrapping belongs in a data migration or an explicit, `IsAdmin`-gated action — not in a read path. If a first-run bootstrap is genuinely needed, keep it in `_provision_client_if_unstaffed` (`accounts/views.py:40-63`), which already claims a vacant Admin seat but correctly restricts that to `user.is_superuser`.

2. **Make role resolution deterministic.** In `backend/accounts/permissions.py:11`, `def get_user_role`, prefer the highest privilege rather than an arbitrary row:

```python
assignment = (
    TeamRoleAssignment.objects
    .filter(assigned_user=user)
    .order_by("role_name")     # 'Admin' sorts before 'Booking Manager'
    .first()
)
```

Relying on alphabetical luck is fragile; if you add roles later, replace this with an explicit precedence map.

**Ripple effects.** After removing the auto-claim, a fresh deployment has **no Admin** until one is assigned — you need a deliberate bootstrap path. Use `python manage.py createsuperuser` and sign in through the CRM: `_provision_client_if_unstaffed` will claim the vacant seat for the superuser. Document this in the deployment notes, and see **F-4** in `SecurityFeatures.md` for the broader single-Admin recovery gap this exposes. No migration required.

**Verification.** Seed the DB with a vacant Admin seat (`TeamRoleAssignment.objects.filter(role_name='Admin').update(assigned_user=None)`) and a Booking Manager account. As that Booking Manager, `GET /api/accounts/team-roles/`. Then assert `TeamRoleAssignment.objects.get(role_name='Admin').assigned_user is None` — the seat must still be vacant — and that `GET /api/accounts/team-roles/me/` still reports `"role": "Booking Manager"`. Add this as a regression test in `backend/accounts/tests.py`.

**Why (preserved reasoning).** Traced: Booking Manager passes `IsStaffMember`; `IsAdminOrReadOnly` allows GET; `get_queryset` writes `assigned_user` when the seat is null; `SET_NULL` makes vacancy reachable through ordinary offboarding. Stale if `get_queryset` no longer writes.

---

#### H-4 — A Client can destroy Invoice and Payment financial records by deleting their own booking
**Severity:** HIGH · **Class:** Broken Access Control / Data Integrity
**OWASP:** A01:2025, A08:2025 · **ASVS 5.0:** 8.2.2, 8.3.1
**Status: FIXED 2026-08-25** — `BookingViewSet.get_permissions` now requires `IsStaffMember` for `destroy`; Clients can no longer delete a booking (and its Invoice/Payment) at all — only staff can, matching how `payments/views.py` already gates invoice deletion. Fixed together with `M-5` as the audit recommended.

**Location** — `backend/booking/views.py:373-413`, `class BookingViewSet` → `def perform_destroy`; permission set at `backend/booking/views.py:59` (`permission_classes = [IsAuthenticated]`); the destructive lines are `views.py:399-405`:

```python
with transaction.atomic():
    if hasattr(instance, 'invoice') and instance.invoice:
        Payment.objects.filter(invoice=instance.invoice).delete()
        instance.invoice.delete()
    instance.delete()
```

**Evidence.** `BookingViewSet` is a full `ModelViewSet` with only `IsAuthenticated`, and `http_method_names` is not restricted (contrast `WaitlistViewSet` at line 423, which *does* restrict methods). `get_queryset` (line 72-87) scopes a Client to `Booking.objects.filter(client__email__iexact=user.email)` — correct isolation, so they can only delete **their own** booking. But deleting their own booking hard-deletes the associated `Invoice` and all its `Payment` rows.

This directly contradicts the design intent stated elsewhere in the codebase: `payments/views.py:22` and `:155` both declare *"Payments is a Staff-only module (Admin or Booking Manager) — Clients never see it"*, and invoice `destroy` is further restricted to Admin alone (`payments/views.py:86-88`). The booking-delete path bypasses both.

**Attack scenario.** A **Client** with an unpaid — or, worse, a *paid* — booking issues `DELETE /api/bookings/{their_own_id}/`. The booking, its invoice, and the payment record showing they owe or paid money all vanish permanently. There is no soft delete, no audit log (see **F-1**), and `Payment.marked_by` — the only attribution field in the system — is destroyed with the row. A client can erase evidence of a disputed or refunded transaction; a business loses its financial record with no way to reconstruct it.

**Impact.** Irreversible destruction of financial records by the least-privileged authenticated actor, defeating the Staff-only boundary the payments module deliberately establishes.

**Remediation.** Clients should cancel, not delete. Restrict `destroy` to staff:

```python
# backend/booking/views.py — in BookingViewSet
from accounts.permissions import IsStaffMember  # add to existing import on line 8

def get_permissions(self):
    if self.action == "destroy":
        return [IsAuthenticated(), IsStaffMember()]
    return super().get_permissions()
```

A Client who wants to withdraw should `PATCH` `status` to `CANCELLED`, which already frees the slot and triggers waitlist notification (`perform_update`, lines 281-286) — but note that `status` is currently writable by clients in a way that needs its own tightening; see **M-5**, which should be fixed together with this.

Separately, consider whether *anyone* should hard-delete an invoice. A stronger fix preserves the financial record even for staff deletes: change `perform_destroy` to stop cascading into `Payment`/`Invoice`, and instead mark the booking cancelled, or move `Invoice`/`Payment` to a soft-delete (`is_void` + `voided_by` + `voided_at`) so the audit trail survives.

**Ripple effects.** If the Client Portal UI currently offers a "Delete booking" button, it must be relabelled/rewired to the cancel (PATCH `status=CANCELLED`) flow, or it will start returning 403 — check `frontend/src/pages/` for the client-side booking list component. If you adopt the soft-delete option, that requires a migration on `payments.Invoice` and `payments.Payment`. No env var or deploy change.

**Verification.** As a Client, `DELETE /api/bookings/{own_id}/` **must return 403**, and `Invoice.objects.filter(booking_id=...)` must still exist afterwards. As a Booking Manager the same request should still succeed (or be restricted further per the decision above). Add a regression test in `backend/booking/tests.py` (currently a 1-line stub).

**Why (preserved reasoning).** Traced: Client JWT → `IsAuthenticated` passes → `get_queryset` returns their own booking → `perform_destroy` cascades into `Payment` and `Invoice` rows that `payments/views.py` otherwise gates behind `IsStaffMember` and Admin-only destroy. Stale if `destroy` gains a staff permission or the cascade is removed.

---

#### H-5 — The password login endpoint has no rate limiting at all
**Severity:** HIGH · **Class:** Authentication Failure
**OWASP:** A07:2025 · **ASVS 5.0:** 6.3.1 [L1] — "controls prevent credential stuffing and brute force"
**Status: PARTIALLY FIXED 2026-08-25** — added `ThrottledTokenObtainPairView` (scope `login`, 5/min) and `ThrottledTokenRefreshView` (scope `token_refresh`, 20/min), wired into `accounts/urls.py`. **`L-5` (shared cache) is still open**, so this throttle is per-worker, not global, until the cache backend moves off `LocMemCache` — see that entry for why this matters.

**Location**
- `backend/accounts/urls.py:18` — `path("login/", TokenObtainPairView.as_view(), name="token-obtain-pair")`
- Reachable at **both** `/api/accounts/login/` and `/api/auth/login/` (`backend/bookings/urls.py:9-10` includes `accounts.urls` twice under two prefixes)
- Related config: `backend/bookings/settings.py:143-144`

**Evidence.** `settings.py` sets `DEFAULT_THROTTLE_CLASSES = ("rest_framework.throttling.ScopedRateThrottle",)` with rates for exactly three scopes: `google_auth`, `otp_request`, `otp_verify`. **DRF's `ScopedRateThrottle` is inert unless the view defines a `throttle_scope` attribute** — with no scope, `allow_request()` returns `True` unconditionally. `TokenObtainPairView` is SimpleJWT's stock class used as-is, with no subclass and no `throttle_scope`.

The three custom auth views *do* set it correctly (`accounts/views.py:73`, `:122`, `:154` — verified, and this part is well done). The password path was simply missed. Because `ScopedRateThrottle` is the only default throttle class, there is also no `AnonRateThrottle`/`UserRateThrottle` baseline to catch it — see **F-6** in `SecurityFeatures.md`.

**Attack scenario.** An **Anonymous** attacker harvests staff email addresses — trivially, via **H-1**'s open `/api/resources/staff/` endpoint, which returns every staff username and email — then runs unlimited-rate credential stuffing against `POST /api/accounts/login/`. There is no lockout, no backoff, no CAPTCHA, no breached-password check (**F-3**), and no MFA on the Admin seat (**F-2**). A successful hit on the single Admin account is total system compromise. Nothing is logged (**F-1**), so the attempt is invisible.

**Impact.** Unauthenticated, unlimited-rate path to staff and Admin account takeover. H-1 supplies the usernames; this supplies the unlimited attempts.

**Remediation.** Subclass the view and give it a scope. In `backend/accounts/views.py`:

```python
from rest_framework_simplejwt.views import TokenObtainPairView

class ThrottledTokenObtainPairView(TokenObtainPairView):
    throttle_classes = [ScopedRateThrottle]      # ScopedRateThrottle already imported at line 7
    throttle_scope = "login"
```

In `backend/accounts/urls.py:18`, point the route at it:

```python
path("login/", ThrottledTokenObtainPairView.as_view(), name="token-obtain-pair"),
```

And add the rate in `backend/bookings/settings.py:144`:

```python
"DEFAULT_THROTTLE_RATES": {
    "google_auth": "10/min", "otp_request": "5/min", "otp_verify": "10/min",
    "login": "5/min",        # add
    "token_refresh": "20/min",  # add if you also scope TokenRefreshView (recommended)
},
```

Apply the same treatment to `TokenRefreshView` (`urls.py:22`), which is likewise unscoped.

**Ripple effects.** DRF throttling stores counters in the **default cache**, which is currently `LocMemCache` (`settings.py:146-152`) — per-process and wiped by `cache.clear()` (see **L-4** and **L-5**). For this throttle to be meaningful in production, move the cache to Redis, or at minimum understand that with N Daphne workers the effective limit is N×5/min. Fixing L-5 is a prerequisite for H-5 being genuinely effective. No migration; add nothing to `.env.example` unless you introduce Redis (then add `REDIS_URL`).

**Verification.** Issue 10 rapid `POST /api/accounts/login/` requests with a wrong password from one IP: requests 6+ must return **429**, not 401. Confirm the same for `/api/auth/login/` (the duplicate prefix). Add a test in `backend/accounts/tests.py` asserting the 429.

**Why (preserved reasoning).** Traced: `DEFAULT_THROTTLE_CLASSES` is `ScopedRateThrottle` only → a view with no `throttle_scope` is unthrottled → `TokenObtainPairView` is used unmodified at `urls.py:18`. Stale if the login route is replaced with a scoped subclass or a global `AnonRateThrottle` is added.

---

### MEDIUM

---

#### M-1 — Logout is client-side only; refresh tokens stay valid for 7 days after sign-out
**Severity:** MEDIUM · **Class:** Session Management Failure
**OWASP:** A07:2025 · **ASVS 5.0:** 7.4.1 [L1] — "after logout or expiry, the session cannot be used again"
**Status: FIXED 2026-08-27** — `accounts/views.py::LogoutView` (`POST /api/accounts/logout/`) blacklists the submitted refresh token server-side; idempotent on a missing/already-blacklisted token. `ACCESS_TOKEN_LIFETIME` shortened from 1 day to 15 minutes — safe now that `frontend/src/api/axiosInstance.js` has a refresh-on-401 interceptor (added alongside this fix; previously there was none, exactly as this entry noted). Both frontend logout paths (`App.js` and the separately-implemented `ClientSidebar.js`) now call the real endpoint via a shared `frontend/src/api/authService.js::logout()` instead of only clearing `localStorage`.

**Location**
- `frontend/src/App.js:136-138` — logout handler: `localStorage.removeItem('access_token' / 'refresh_token' / 'user')`
- `frontend/src/components/ClientSidebar.js:10` — `localStorage.clear()`
- `backend/accounts/urls.py:17-24` — no logout/blacklist route is registered
- `backend/bookings/settings.py:36` — `rest_framework_simplejwt.token_blacklist` **is** in `INSTALLED_APPS`
- `backend/bookings/settings.py:161-166` — `ACCESS_TOKEN_LIFETIME` 1 day, `REFRESH_TOKEN_LIFETIME` 7 days

**Evidence.** Logging out only deletes tokens from browser storage. No request is made to the server, and no endpoint exists to blacklist the refresh token. The `token_blacklist` app is installed and `BLACKLIST_AFTER_ROTATION: True` is set — so the machinery is present and migrated, but is only exercised on rotation, never on logout.

**Attack scenario.** A **Client or staff member** signs out on a shared or public machine. Their refresh token was already captured — from browser storage by another user of that machine, from a proxy access log (see **M-3** for the WebSocket variant), or from a backup. Because logout never revoked it server-side, the attacker exchanges it at `/api/accounts/token/refresh/` for fresh access tokens for up to **7 days**, and each rotation extends their foothold. The victim believes they have signed out.

**Impact.** Sign-out provides no actual session termination. Combined with the 1-day access-token lifetime, a stolen token has a long useful life and there is no way to revoke it — no admin "sign out everywhere", no per-session record.

**Remediation.** Add a real logout endpoint. In `backend/accounts/views.py`:

```python
from rest_framework_simplejwt.tokens import RefreshToken as RT
from rest_framework.permissions import IsAuthenticated as IsAuthed

class LogoutView(APIView):
    permission_classes = [IsAuthed]

    def post(self, request):
        try:
            RT(request.data["refresh"]).blacklist()
        except (KeyError, TokenError):
            # Idempotent: an absent or already-blacklisted token is still a successful logout.
            pass
        return Response(status=status.HTTP_205_RESET_CONTENT)
```

Register it in `backend/accounts/urls.py`: `path("logout/", LogoutView.as_view(), name="logout")`. Then in `frontend/src/App.js`, make the logout handler `await api.post('/accounts/logout/', { refresh: localStorage.getItem('refresh_token') })` before clearing storage, ignoring any error so sign-out never blocks.

Consider also shortening `ACCESS_TOKEN_LIFETIME` to ~15 minutes (`settings.py:162`); with rotation already enabled, this bounds the damage window of any leaked access token and is the single highest-value change here.

**Ripple effects.** `token_blacklist` is already installed, so its migrations should already be applied — confirm with `python manage.py showmigrations token_blacklist`; if not, run migrations at deploy. Blacklist tables grow unboundedly: schedule `python manage.py flushexpiredtokens` periodically. Shortening the access-token lifetime makes 401s routine, so the frontend needs a refresh-on-401 interceptor in `frontend/src/api/axiosInstance.js` — which currently has **no response interceptor at all** (it only attaches the token on request). Add that before shortening the lifetime, or users will be logged out mid-session.

**Verification.** Capture a refresh token, log out through the UI, then `POST /api/accounts/token/refresh/` with the captured token — it must return **401**, not a new access token.

**Why (preserved reasoning).** Traced: no logout route in `accounts/urls.py`; frontend logout is pure `localStorage` mutation; `token_blacklist` installed but only reached via rotation. Stale if a logout/blacklist endpoint is added.

---

#### M-2 — Google Calendar encryption key is `sha256(SECRET_KEY)` — no independent rotation path
**Severity:** MEDIUM · **Class:** Cryptographic Failure / Key Management
**OWASP:** A04:2025 · **ASVS 5.0:** 11.4.1, 14.x (data protection at rest)
**Status: FIXED 2026-08-27** — `booking/crypto.py` now reads `settings.CALENDAR_TOKEN_KEYS`, independent of `SECRET_KEY`, using `MultiFernet` (comma-separated, first key encrypts, all keys decrypt) for rotation without downtime. `CALENDAR_TOKEN_KEY` env var, dev-only fallback when `DEBUG=true`, raises `ImproperlyConfigured` if unset in production (same fail-closed pattern as `H-2`). Rotation supported via `python manage.py rotate_calendar_key` (`booking/management/commands/`). **Deployment note carried over from this entry's own remediation**: any *existing* `GoogleCalendarCredential` row encrypted under the old `sha256(SECRET_KEY)` scheme will not decrypt under the new key and must be reconnected once via `/admin-tools/google-calendar/connect/` after this deploys — documented in `.env.example`.

**Location** — `backend/booking/crypto.py:14-16`, `def _fernet`

```python
def _fernet():
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)
```

Consumers: `backend/booking/admin_calendar_views.py:98` (`encrypt_token`) and `backend/booking/google_calendar.py:31` (`decrypt_token`), protecting `GoogleCalendarCredential.refresh_token_encrypted` (`backend/booking/models.py:131`).

**Evidence.** The Fernet key is a plain single-pass SHA-256 of `DJANGO_SECRET_KEY` — no salt, no KDF, no work factor, and no independent secret. The module's own docstring states the trade-off deliberately ("so no extra required env var is needed"), so this was a considered choice, not an oversight. Encryption is otherwise correct: Fernet is authenticated AES-128-CBC + HMAC, and the token is genuinely never stored in plaintext.

**Three concrete consequences.**
1. **No rotation path.** Rotating the Calendar encryption key is impossible without rotating `SECRET_KEY`, which simultaneously invalidates every session and every issued JWT. The two lifecycles are welded together, so in practice neither ever gets rotated.
2. **Silent breakage on rotation.** If `SECRET_KEY` *is* rotated, `decrypt_token` returns `None` (it catches `InvalidToken` and returns `None`, `crypto.py:26-27`), and `google_calendar.py:32-33` degrades to the error string *"Stored Google Calendar credential could not be decrypted."* Bookings continue to succeed while Calendar sync silently stops — a correct fail-safe, but one that needs a documented re-connect step.
3. **Interaction with H-2.** If `SECRET_KEY` is the committed default `"change-this-before-production"`, the Fernet key is *publicly derivable* — the refresh token is then effectively stored in plaintext to anyone with database read access. The encryption provides real protection only insofar as H-2 is fixed.

**Attack scenario.** An attacker with read access to the database *but not* the application environment — a leaked backup, a misconfigured `DB_SSLMODE`, a compromised read replica — obtains `refresh_token_encrypted`. Under a strong `SECRET_KEY` they cannot decrypt it and the control holds. Under the default key (H-2) they derive the Fernet key in one line and obtain a long-lived Google Calendar refresh token for the **business account**, letting them read and manipulate the company calendar.

**Impact.** Bounded — it requires either `SECRET_KEY` compromise or the H-2 default-key condition. The more probable real-world harm is operational: there is no way to rotate this key after a suspected exposure without a full session/JWT invalidation, so the organisation's only response to a leak is one it will be reluctant to take.

**Remediation.** Give the Calendar token its own secret with its own lifecycle. In `backend/booking/crypto.py`:

```python
from django.core.exceptions import ImproperlyConfigured

def _fernet():
    key = getattr(settings, "CALENDAR_TOKEN_KEY", "")
    if not key:
        raise ImproperlyConfigured("CALENDAR_TOKEN_KEY must be set to a Fernet key.")
    return Fernet(key.encode())
```

In `backend/bookings/settings.py`, add `CALENDAR_TOKEN_KEY = os.getenv("CALENDAR_TOKEN_KEY", "")`. Generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.

For rotation support, prefer `MultiFernet` — accept a comma-separated list where the first key encrypts and all keys decrypt, enabling zero-downtime rotation followed by a re-encrypt pass.

**Ripple effects.** Add `CALENDAR_TOKEN_KEY` to `backend/.env.example` (with a comment showing the generation command) and set it as an Azure App Service Application Setting. **Migration concern:** any *existing* `GoogleCalendarCredential` row was encrypted under the old derived key and will not decrypt under the new one. Either write a one-off data migration that decrypts with the old scheme and re-encrypts with the new, or simply delete the row and have the Admin re-run the OAuth handshake at `/admin-tools/google-calendar/connect/` (simplest, and the flow already deletes and recreates the singleton row at `admin_calendar_views.py:95-101`). Document the chosen path. See **F-5** in `SecurityFeatures.md` for the wider key-management gap.

**Verification.** With `CALENDAR_TOKEN_KEY` set, reconnect Calendar and confirm a booking syncs. Then change `DJANGO_SECRET_KEY` and confirm Calendar sync **still works** — that is the proof the two secrets are decoupled. With `CALENDAR_TOKEN_KEY` unset, the app must raise `ImproperlyConfigured` rather than silently deriving a key.

**Why (preserved reasoning).** Traced `crypto.py:_fernet` → `settings.SECRET_KEY` → shared with SimpleJWT signing and Django sessions; confirmed the only two call sites are the OAuth callback and the Calendar service. Stale if `_fernet` reads a dedicated setting.

---

#### M-3 — JWT access token is sent in the WebSocket URL query string
**Severity:** MEDIUM · **Class:** Data Protection / Information Exposure
**OWASP:** A04:2025 · **ASVS 5.0:** 14.2.1 [L1] — "sensitive data travels in the body or headers, never the URL or query string"
**Status: FIXED 2026-08-27** — implemented this entry's own "lower-effort alternative": the token now travels as a WebSocket subprotocol (`new WebSocket(url, ["jwt", token])` in `frontend/src/hooks/useNotificationSocket.js`) instead of a `?token=` query param. `notifications/middleware.py::JWTAuthMiddleware` reads `scope["subprotocols"]` instead of the query string; `notifications/consumers.py` echoes `subprotocol="jwt"` back on accept (required by the WS handshake once a client offers a subprotocol list). Verified end-to-end with `channels.testing.WebsocketCommunicator` (`notifications/tests.py`), including that the old query-string transport no longer authenticates at all. Same caveat as before: shortening `ACCESS_TOKEN_LIFETIME` (now done, see `M-1`) further bounds any residual exposure.

**Location**
- `frontend/src/hooks/useNotificationSocket.js:26` — `new WebSocket(\`${WS_BASE_URL}/ws/notifications/?token=${encodeURIComponent(token)}\`)`
- `backend/notifications/middleware.py:33-37`, `class JWTAuthMiddleware.__call__` — reads `parse_qs(query_string).get("token")`

**Evidence.** The middleware docstring correctly explains *why* (browsers cannot set an `Authorization` header on a WebSocket handshake) and the authentication itself is **properly implemented** — the token is cryptographically validated via `AccessToken(token)`, and `NotificationConsumer.connect` (`consumers.py:12-19`) rejects unauthenticated connections with close code 4001 and scopes each socket to a per-user group. This finding is about token *transport*, not about missing authentication.

**Attack scenario.** The full JWT appears in the handshake URL and is therefore recorded wherever URLs are recorded: Azure App Service / reverse-proxy access logs, any APM or CDN in front of the app, and browser history. Anyone with log-read access — an operations engineer, a log-aggregation vendor, or an attacker who obtains a log archive — recovers a **live bearer token**, valid for up to 24 hours (`ACCESS_TOKEN_LIFETIME`, `settings.py:162`) and unrevocable because there is no logout blacklist (**M-1**). They replay it against the entire REST API, not just the socket.

**Impact.** Credential leakage into logs, with a 24-hour replay window and no revocation. Aggravated by M-1 and by the long access-token lifetime.

**Remediation.** Use a short-lived, single-purpose ticket instead of the long-lived access token. Add an authenticated REST endpoint (e.g. `POST /api/notifications/ws-ticket/`) that returns an opaque, random, ~30-second, single-use ticket stored in the cache and bound to the user id; have the frontend request a ticket immediately before opening the socket and pass `?ticket=...`; have `JWTAuthMiddleware` resolve and immediately consume it. A leaked log line then contains a value that expired seconds after it was written.

The lower-effort alternative — used widely and acceptable here — is the `Sec-WebSocket-Protocol` subprotocol header: pass the token as a subprotocol value (`new WebSocket(url, ["jwt", token])`) and read it from `scope["subprotocols"]` in the middleware, keeping it out of the URL. This requires echoing the accepted subprotocol back in `consumers.py:19` (`await self.accept(subprotocol="jwt")`).

Whichever you choose, also shorten `ACCESS_TOKEN_LIFETIME` per **M-1**.

**Ripple effects.** Both options require coordinated changes to `frontend/src/hooks/useNotificationSocket.js` and `backend/notifications/middleware.py`, deployed together — the socket will fail to connect if only one side ships. The ticket approach additionally depends on a shared cache across processes if you run multiple Daphne workers (see **L-4** / `CHANNEL_LAYERS` note in **I-5**). No migration.

**Verification.** Open the app with the browser devtools Network tab filtered to WS and confirm the handshake URL no longer contains the token. Check the Azure App Service log stream for the WebSocket request line and confirm no JWT appears in it.

**Why (preserved reasoning).** Traced the token from `localStorage` → query string → proxy-logged URL, and confirmed the same token is a valid REST bearer credential. Stale if the handshake stops carrying the access token in the URL.

---

#### M-4 — `cache_page` on per-user endpoints can serve one user's data to another
**Severity:** MEDIUM · **Class:** Broken Access Control / Security Misconfiguration
**OWASP:** A01:2025, A02:2025 · **ASVS 5.0:** 8.2.2
**Status: FIXED 2026-08-27** — took this entry's own recommended "cleanest fix": removed `cache_page`/`vary_on_headers` entirely from `notifications/views.py::NotificationViewSet.list` and `dashboard/views.py::DashboardSummaryView.get` rather than trying to key the cache more carefully. Both are single indexed/aggregated queries — cheap enough that caching wasn't buying much, and removing it closes the cross-user disclosure outright rather than mitigating it. `resources/views.py`'s `cache_page` usage was left as-is per this entry's own note (its querysets are global/identical for every caller, so there's nothing to leak).

**Location**
- `backend/notifications/views.py:21-24` — `NotificationViewSet.list`, decorated `@method_decorator(cache_page(60 * 5))` + `@method_decorator(vary_on_headers("Authorization"))`
- `backend/dashboard/views.py:20-22` — `DashboardSummaryView.get`, same pair
- `backend/resources/views.py:17-19`, `:28-30`, `:39-41` — same pair on all three `list` methods

**Evidence.** `cache_page` keys entries on the request URL plus whatever headers the response's `Vary` names. `vary_on_headers("Authorization")` is present and does the right thing **for JWT-authenticated requests**: distinct tokens produce distinct cache keys. I verified this rather than assuming it, and for the normal React→JWT path the caching is safe.

The gap is the **session-authenticated path**. `settings.py:134-137` enables `SessionAuthentication` alongside JWT in `DEFAULT_AUTHENTICATION_CLASSES`. A request authenticated by session cookie carries **no `Authorization` header at all**, so `Vary: Authorization` collapses to a single shared cache key for every such user. `NotificationViewSet.get_queryset` (`views.py:17-19`) correctly scopes rows to `recipient=self.request.user` — but that filtering happens *before* the response is cached, and the cache is then keyed identically for all cookie-authenticated callers.

**Attack scenario.** Two staff members are signed into Django admin (`/admin/`) in the same browser context — a routine state, since `/admin/` is the only way to manage several models here. Staff member A's browser requests `/api/notifications/` and is authenticated by session cookie; the response — A's private notifications — is cached under a key containing no user component. Within the 5-minute window, staff member B makes the same request and receives **A's notifications**. The same mechanism applies to `dashboard`, whose payload is scoped `created_by=user`.

**Impact.** Cross-user disclosure of private notification content and dashboard metrics. Genuinely constrained — it needs concurrent cookie-authenticated API use, which the React SPA never does — but it is a real fail-open in a caching layer, and the blast radius grows if session auth is ever used more widely.

**Remediation.** The cleanest fix is to stop HTTP-caching per-user endpoints. Remove the `cache_page` decorator from `notifications/views.py:21` and `dashboard/views.py:20`. These endpoints are cheap; `NotificationViewSet.list` is a single indexed query.

If caching must stay, do it the way the rest of this codebase already does it — an explicit, user-scoped key inside the method, as `payments/views.py:51-67` and `booking/views.py:154-169` do:

```python
cache_key = f"notifications_{request.user.id}_{page_param}"
```

That pattern is immune to the header problem because the user id is *in the key*, not inferred from a header that may be absent.

`resources/views.py` is unaffected by the disclosure (its querysets are global, identical for everyone) — but once **H-1** adds `IsStaffMember` there, revisit whether caching is still wanted; it is low value either way.

**Ripple effects.** Removing `cache_page` slightly increases DB load on the notification poll — negligible relative to the risk. If you keep caching, remember `LocMemCache` is per-process (**L-4**), so cached entries differ per worker regardless. No migration, no config change. Also consider dropping `SessionAuthentication` from `DEFAULT_AUTHENTICATION_CLASSES` entirely if the SPA is the only API consumer, which would eliminate this class of problem and reduce CSRF surface at the same time.

**Verification.** Sign two different users into `/admin/` in two browser profiles. From each, request `/api/notifications/` using only cookies (no `Authorization` header) within 5 minutes. Each must receive **only their own** notifications. Assert `Cache-Control`/`Vary` on the response and confirm no `cache_page` key is shared.

**Why (preserved reasoning).** Traced: `SessionAuthentication` is enabled globally → a cookie-authenticated request has no `Authorization` header → `Vary: Authorization` yields one shared key → `cache_page` stores a per-user response under it. Stale if `cache_page` is removed from these views or `SessionAuthentication` is dropped.

---

#### M-5 — Clients can change their own booking's `status`, enabling self-confirmation and waitlist email abuse
**Severity:** MEDIUM · **Class:** Broken Access Control / Business Logic
**OWASP:** A01:2025, A06:2025 · **ASVS 5.0:** 2.3.1 (business logic sequencing), 8.2.2
**Status: FIXED 2026-08-25** — added `BookingSerializer.validate_status`: Clients cannot set status on create, can only transition to `CANCELLED`, and cannot re-cancel an already-cancelled booking (which is what stops the waitlist-email amplification). Fixed together with `H-4`.

**Location** — `backend/booking/serializers.py:53-69`, `class BookingSerializer.Meta`:

```python
fields = "__all__"
read_only_fields = (
    "created_by", "created_at", "updated_at", "client_full_name",
    "rate_snapshot", "payment_status",
    "google_event_id", "calendar_sync_status", "calendar_sync_error",
)
```

Consequence path: `backend/booking/views.py:244-320`, `class BookingViewSet.perform_update`.

**Evidence.** `status` is **absent** from `read_only_fields`, and `fields = "__all__"` therefore exposes it as writable. `BookingViewSet` allows Clients to `PATCH` their own bookings (`permission_classes = [IsAuthenticated]`, `views.py:59`; `get_queryset` scopes to their own rows). The serializer's `validate()` correctly pins `client`, and `_apply_backend_pricing` correctly strips client-supplied `price` — the pricing defence is genuinely solid (see *Areas already done well*) — but nothing constrains `status` transitions.

Note the contrast: `payment_status` **is** protected, with an explicit comment at `serializers.py:62-64` stating it "may only ever change via the Invoice pay/unpaid/refund actions". `status` was simply not given the same treatment.

**Attack scenario.** A **Client** sends `PATCH /api/bookings/{own_id}/ {"status": "CONFIRMED"}` and self-approves a booking that the business's workflow intends staff to confirm. More damaging is the notification amplification: setting `status` to `CANCELLED` satisfies `just_cancelled` in `perform_update` (`views.py:282`), which calls `notify_waitlist_for_freed_slot(...)` — **emailing every client waitlisted for that slot** (`booking/emails.py:207-228`) — plus `_notify_waitlist_slot_available_in_app`. Because booking updates have no throttle at all (**F-6**), a Client holding one booking on a popular slot can repeatedly toggle status and drive outbound mail to every waitlisted third party, burning the Gmail SMTP quota and turning the business's own domain into a spam source. They can also mark bookings `COMPLETED`, corrupting the Admin reports and cancellation-rate metrics in `reports/services.py`.

**Impact.** Business-workflow bypass, third-party email abuse from the company's SMTP identity, and pollution of the metrics the Admin uses to run the business.

**Remediation.** Constrain which statuses a Client may set, and to what. In `backend/booking/serializers.py`, add to `BookingSerializer`:

```python
def validate_status(self, value):
    request = self.context.get("request")
    user = request.user if request else None
    if user and not is_staff_member(user):          # is_staff_member already imported, line 5
        if not self.instance:
            # Clients never choose the initial status; the model default (PENDING) applies.
            raise serializers.ValidationError("You cannot set a booking's status.")
        if value != Booking.BookingStatus.CANCELLED:
            raise serializers.ValidationError("You can only cancel your own booking.")
        if self.instance.status == Booking.BookingStatus.CANCELLED:
            raise serializers.ValidationError("This booking is already cancelled.")
    return value
```

This keeps the legitimate client-cancel flow (which **H-4** redirects clients toward) while blocking self-confirmation, self-completion, and repeat-cancel toggling. Guarding the already-`CANCELLED` case is what stops the email amplification, since `just_cancelled` requires a transition *out of* an active status.

Fix this together with **H-4** — they are the same surface, and H-4's remediation depends on cancel being the sanctioned client path.

**Ripple effects.** If the Client Portal UI exposes a status dropdown, restrict it to Cancel. Add a per-user throttle on booking writes (see **F-6**) so waitlist notification cannot be driven in a loop by any other means. No migration.

**Verification.** As a Client: `PATCH {"status": "CONFIRMED"}` on your own booking must return **400**; `PATCH {"status": "CANCELLED"}` must succeed; a second `PATCH {"status": "CANCELLED"}` must return 400 and must send **no** further waitlist emails. Assert the outbound mail count with `django.core.mail.outbox` in a test in `backend/booking/tests.py`.

**Why (preserved reasoning).** Traced: `status` writable → Client `PATCH` reaches `perform_update` → `just_cancelled` branch → `notify_waitlist_for_freed_slot` emails third parties, with no throttle on the endpoint. Stale if `status` is added to `read_only_fields` or a `validate_status` guard is introduced.

---

#### M-6 — Backend dependencies are unpinned ranges with no lock file
**Severity:** MEDIUM · **Class:** Software Supply Chain Failure
**OWASP:** A03:2025 · **ASVS 5.0:** 15.x (secure coding and architecture / dependency management)
**Status: PARTIALLY FIXED 2026-08-27** — `requirements.txt` now pins every dependency to the exact version already running (`Django==5.2.16`, etc.) instead of open ranges, so a build of a given commit is reproducible rather than re-resolving to "whatever's newest on PyPI today." **Not done**: the fuller `pip-compile --generate-hashes` + `--require-hashes` lock-file setup this entry's own remediation describes, which would add integrity verification (not just version pinning) and is a materially bigger change to the build (new lock file, Dockerfile install step, a process for regenerating it). Pair with `F-10` (CI dependency scanning, still open) when that lands.

**Location** — `backend/requirements.txt:1-13`; consumed at `backend/Dockerfile:11-12` (`COPY requirements.txt .` / `RUN pip install --no-cache-dir -r requirements.txt`).

**Evidence.** Every backend dependency is a floor-to-ceiling range — `Django>=5.0,<6.0`, `cryptography>=42,<50`, `reportlab>=4.0,<6.0`, and so on. There is no `requirements.lock`, no `pip-tools` output, no hashes. Each container build re-resolves to whatever is newest on PyPI at build time, so two builds of the *same commit* can ship different dependency trees, and a compromised or yanked upstream release is adopted automatically with no review gate.

I checked the currently installed versions in `backend/.venv` and **found no known-vulnerable packages** — Django 5.2.16, cryptography 49.0.0, djangorestframework 3.17.1, simplejwt 5.5.1, requests 2.34.2, urllib3 2.7.0, reportlab 5.0.0, channels 4.3.2, daphne 4.2.3, google-auth 2.56.2. This finding is about build reproducibility and the absence of a review gate, not about a specific vulnerable version today.

Note the asymmetry: the **frontend is done correctly** — `frontend/package-lock.json` exists and CI uses `npm ci` (`azure-static-web-apps-*.yml:36`), which is exactly right.

**Impact.** Unreproducible builds; a supply-chain compromise or a breaking release in any transitive dependency reaches production without anyone choosing to upgrade. Rollback is unreliable because redeploying an old commit does not restore its dependency set.

**Remediation.** Introduce a lock file and install from it.

1. Keep `requirements.txt` as the human-edited direct-dependency list (rename to `requirements.in` if adopting `pip-tools`).
2. Generate a fully pinned, hashed lock: `pip-compile --generate-hashes -o requirements.lock requirements.txt`.
3. Change `backend/Dockerfile:11-12` to copy and install the lock:

```dockerfile
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
```

`--require-hashes` is what turns the lock into an integrity control rather than just a version list.

**Ripple effects.** `requirements.lock` must be committed and regenerated deliberately whenever a dependency changes — add that step to the contribution notes. The `.dockerignore` (`backend/.dockerignore`) does not exclude it, so no change needed there. Pair this with automated dependency scanning in CI (**F-10** in `SecurityFeatures.md`), which is what turns pinning from a freeze into a managed upgrade process — pinning without scanning trades one risk for another.

**Verification.** Build the image twice from the same commit and confirm `pip freeze` output is byte-identical. Corrupt one hash in the lock and confirm the build **fails** rather than proceeding.

**Why (preserved reasoning).** Traced `requirements.txt` ranges → `Dockerfile` build-time resolution → non-deterministic image contents; confirmed no lock file exists anywhere under `backend/`. Stale if a lock file is added and the Dockerfile installs from it.

---

### LOW

---

#### L-1 — Container runs as root
`backend/Dockerfile` has no `USER` directive, so Daphne runs as uid 0 (`Dockerfile:22`). Any RCE or path-traversal bug becomes root inside the container, and a writable-filesystem escape is materially easier. **Fix:** add `RUN adduser --system --no-create-home appuser` and `USER appuser` before `CMD`; ensure `/app` is readable by that user. Verify with `docker run --rm <image> id` returning a non-zero uid. **Status: OPEN** (A02:2025)

---

#### L-2 — Production security headers not configured
`backend/bookings/settings.py` sets `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` (lines 182-183) but never sets `SECURE_HSTS_SECONDS`, `SECURE_HSTS_INCLUDE_SUBDOMAINS`, `SECURE_SSL_REDIRECT`, or any Content-Security-Policy. Django's defaults cover `X-Content-Type-Options` and `X-Frame-Options: DENY`, so the gap is transport hardening and CSP. **Fix:** add `SECURE_SSL_REDIRECT = not DEBUG` and `SECURE_HSTS_SECONDS = 31536000` (with `SECURE_HSTS_INCLUDE_SUBDOMAINS = True`) guarded on `not DEBUG`; add CSP via `django-csp` or at the Azure Static Web Apps layer for the frontend. Verify with `python manage.py check --deploy`, which flags exactly these. **Status: OPEN** (A02:2025)

---

#### L-3 — `SECURE_PROXY_SSL_HEADER` is trusted unconditionally
`settings.py:178` sets `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` with no accompanying guarantee that the app is only reachable through the Azure front end. If the container port is ever exposed directly, any client can send `X-Forwarded-Proto: https` and Django will treat a plaintext request as secure, defeating `SECURE_SSL_REDIRECT` and secure-cookie enforcement. Correct and necessary behind App Service; the risk is purely the direct-exposure case. **Fix:** confirm the container is not directly routable, and document the dependency in `.env.example` / deployment notes. **Status: OPEN** (A02:2025)

---

#### L-4 — `cache.clear()` on client writes flushes DRF throttle counters
`backend/clients/views.py:77-82`, `def _clear_client_cache`, falls back to `cache.clear()` when the backend has no `delete_pattern` — which is always, since `LocMemCache` (`settings.py:146-152`) has no such method. So **every** client create/update/delete wipes the entire cache, including the DRF `ScopedRateThrottle` counters for `otp_request`, `otp_verify`, and `google_auth`. A staff member editing clients repeatedly resets the anti-automation window for anonymous attackers. **Fix:** track cache keys explicitly, or move to Redis and use real pattern deletion; never `cache.clear()` a cache shared with throttling. Better: give throttling its own cache alias via `DEFAULT_THROTTLE_CACHE`. Verify by exhausting the OTP throttle, triggering a client update, and confirming the throttle is **still** in effect. **Status: OPEN** (A06:2025)

---

#### L-5 — `LocMemCache` makes throttle counters per-process
`settings.py:146-152` uses `LocMemCache`, which is per-worker and non-shared. With N Daphne/Gunicorn workers, every rate limit is effectively N× its configured value, and counters reset on each restart. This directly weakens **H-5**, **L-4**, and every `throttle_scope` in the app. **Fix:** switch the default cache (or at least the throttle cache) to Redis for any multi-process deployment; add `REDIS_URL` to `.env.example`. Verify by confirming throttle state survives a worker restart. **Status: OPEN** (A06:2025)

---

#### L-6 — CI actions pinned to mutable tags; no least-privilege `permissions` block
Both workflows pin actions to moving major tags (`actions/checkout@v4`/`@v3`, `docker/login-action@v2`, `docker/build-push-action@v3`, `Azure/static-web-apps-deploy@v1`), so a compromised or retagged upstream action executes in a pipeline holding registry credentials and an Azure publish profile. `azure-static-web-apps-*.yml` declares no `permissions:` block, inheriting the repository default `GITHUB_TOKEN` scope. **Fix:** pin actions to full commit SHAs; add `permissions: { contents: read }` to the SWA workflow (the backend workflow's `build` job already does this correctly at line 15-16) and grant more only where needed. Verify by re-running both pipelines. **Status: OPEN** (A03:2025, A08:2025)

---

#### L-7 — Unhandled `InvalidOperation` on malformed discount input returns 500
`backend/payments/services.py:45`, `BillingService.mark_invoice_paid`, evaluates `Decimal(str(discount_amount))` on a value taken straight from `request.data` (`payments/views.py:95`). A non-numeric string raises `decimal.InvalidOperation`, which subclasses `ArithmeticError`, **not** `ValueError` — so the `except ValueError` at `views.py:109` does not catch it and the request 500s. A negative value is also accepted and inflates `total_amount`. Admin-only, so impact is limited to error-handling hygiene and a bad-input path. **Fix:** validate `discount_amount` as a non-negative `DecimalField` in a serializer before calling the service, and catch `(ValueError, InvalidOperation)`. Verify by POSTing `{"discount_amount": "abc"}` to the `pay` action and asserting **400**, not 500. **Status: OPEN** (A10:2025)

---

### INFORMATIONAL / HARDENING

---

#### I-1 — JWT stored in `localStorage` (no XSS sink found)
`frontend/src/api/axiosInstance.js:11` reads `access_token` from `localStorage`; tokens are written there by `components/EmailOtpForm.js:68-70` and `components/GoogleAuthButton.js:23-25`. `localStorage` is readable by any JavaScript on the origin, so this is the classic XSS-exfiltration surface. **I traced for a paired sink and found none:** there is no `dangerouslySetInnerHTML`, `innerHTML`, `document.write`, `eval`, or `new Function` anywhere in `frontend/src/`, and React escapes by default — so there is no XSS→token-theft chain in the application's own code today. This is therefore a **standalone hardening item, not an exploitable finding**: the mitigation is to keep it that way (never introduce `dangerouslySetInnerHTML` for client notes or booking descriptions) and, if defence-in-depth is wanted, move refresh tokens to an `HttpOnly; Secure; SameSite=Strict` cookie. Logout does correctly clear all three keys (`App.js:136-138`), satisfying ASVS 14.3.1. **Status: OPEN**

---

#### I-2 — One-day access-token lifetime is long for a bearer token
`settings.py:162` sets `ACCESS_TOKEN_LIFETIME = timedelta(days=1)`. Because rotation and blacklist-after-rotation are already enabled, a much shorter access token (15 minutes) would cost little and would sharply reduce the value of any token leaked via **M-3** or lifted from storage per **I-1**. Fixing this is a prerequisite for M-1's revocation story being meaningful, and requires a 401-refresh interceptor in `axiosInstance.js` first. **Status: OPEN**

---

#### I-3 — A `frontend/src/.env` exists in git history, but contained no secret
`git log --all --full-history` shows `frontend/src/.env` added in `5620512` and removed in `9947e90`; the blob is still reachable in history. I inspected the **variable names only** and it contained exactly `REACT_APP_GOOGLE_CLIENT_ID` and `REACT_APP_API_BASE_URL` — both public by design (CRA inlines every `REACT_APP_*` value into the shipped JS bundle, and a Google Web client ID is not a secret). **No credential was exposed; no history rewrite is warranted.** Recorded so a future audit does not re-flag it. Separately confirmed: `backend/.env` is correctly ignored (`backend/.gitignore:18`) and **has never been committed**; only `.env.example` files are tracked; `db.sqlite3` is untracked; `backend/.dockerignore` correctly excludes `.env`, `.venv`, `.git`, and `db.sqlite3` from the build context. **Status: CLOSED — no action needed**

---

#### I-4 — `available-slots` discloses other clients' booking IDs to Clients
`backend/booking/views.py:128` sets `entry["booking_id"] = conflict.id` for every caller, while correctly withholding `client_name` and `waitlist_count` from non-staff (lines 129-133). A Client therefore learns the integer IDs of other clients' bookings. Impact is minimal — `BookingViewSet.get_queryset` filters by client email, so those IDs return 404 on retrieve — and the slot's booked/free state is already public to authenticated users by design. Consider omitting `booking_id` for non-staff to avoid handing out enumerable identifiers. **Status: OPEN**

---

#### I-5 — `InMemoryChannelLayer` and `LocMemCache` are single-process only
`settings.py:156-160` uses `channels.layers.InMemoryChannelLayer`; the inline comment already acknowledges it suits a single process and should be swapped for `channels_redis` in a multi-process deployment. With multiple Daphne workers, a notification broadcast from the worker handling the REST write never reaches a socket held by a different worker, so real-time delivery silently degrades. Availability/correctness rather than confidentiality, but it shares a root cause with **L-5** — adopt Redis once and fix both. **Status: OPEN**

---

#### I-6 — Report generation loads all invoices into Python
`backend/reports/services.py:76` and `:107` iterate `Invoice.objects.all()` in full, twice per request, doing arithmetic in Python rather than in the database. Admin-only and cached for 5 minutes, so not an abuse vector today, but it degrades linearly with invoice count and will eventually time out. Replace with `aggregate`/`annotate` queries. Note also that `dashboard/views.py:26` scopes the "business" dashboard to `created_by=user` and `:37-40` filters `Booking.status="PAID"` — a status value that does not exist in `BookingStatus` — so that panel reports 0 revenue. Correctness bugs, flagged here only because they sit in audited files. **Status: OPEN**

---

## Most critical issues

Fix these five before any production exposure:

1. **H-1** — `resources` app is wide open to any self-registered user, leaking the staff roster (which directly enables H-5).
2. **H-5** — password login has zero rate limiting; combined with H-1's harvested emails, this is a straight path to Admin takeover.
3. **H-2** — the app boots with a publicly-known `SECRET_KEY` instead of refusing to start.
4. **H-3** — a Booking Manager becomes Admin by loading a page.
5. **H-4** — a Client can permanently delete financial records.

## Highest-priority hardening

**L-5 / L-4** (move the cache to Redis) is the highest-leverage hardening item, because every rate limit in the system — including the one added by H-5 — is currently per-process and flushable by an unrelated staff action. After that: **M-1** (real logout + shorter access tokens), **L-2** (`manage.py check --deploy` headers), and **L-1** (non-root container).

## Areas already done well

Name these explicitly so a future session does not "fix" what is already correct:

- **Email OTP is properly implemented.** Codes are hashed with `make_password`, never stored raw (`accounts/models.py:56`); `verify_email_otp` (`accounts/services.py:178-218`) is `@transaction.atomic` with `select_for_update`, and **does** enforce all three controls — `MAX_ATTEMPTS` (line 191), expiry (line 188), and `consumed_at` (lines 184, 199). Codes come from `secrets.randbelow`. A 60-second resend cooldown bounds issuance. I verified each of these against the view rather than assuming from the model.
- **Throttle scopes *are* wired up on the three custom auth views** — `accounts/views.py:73` (`google_auth`), `:122` (`otp_request`), `:154` (`otp_verify`). The settings-only trap was checked and these are correct; only the stock `TokenObtainPairView` was missed (**H-5**).
- **Google ID-token verification is correct.** `accounts/services.py:44-59` uses `google_id_token.verify_oauth2_token` with an explicit `audience`, which validates signature, issuer, audience, and expiry, and the code additionally requires `email_verified` to be true before trusting the identity.
- **The Google Calendar OAuth handshake is textbook.** `booking/admin_calendar_views.py` uses a CSPRNG `state` (line 32), stores it in the session, and pops-and-compares it on callback (lines 52-56); both views are `@staff_member_required`; the requested scope is `calendar.events` only (least privilege).
- **WebSocket connections are genuinely authenticated.** `notifications/middleware.py` cryptographically validates the JWT and `consumers.py:12-19` rejects anonymous connections with close code 4001, scoping each socket to a `user_<id>` group. Channels does *not* inherit DRF auth, and this project correctly built that layer itself. Only the token's transport is at issue (**M-3**).
- **The booking write path resists client tampering.** `BookingSerializer.validate` pins `client` to the caller's own record (`serializers.py:97-104`), `_apply_backend_pricing` (`:135-174`) never trusts a client-supplied `price` and re-derives it from a server-side `Service.hourly_rate` snapshot, and `payment_status` is `read_only`. Only `status` slipped through (**M-5**).
- **Client data isolation on bookings and waitlist is correct** — `booking/views.py:87` and `:429` scope non-staff to `client__email__iexact=user.email`, and the email is verified at registration by OTP or by Google's `email_verified` claim.
- **Payments avoid raw card data entirely** — `Payment` stores method, amount, and a `transaction_id` only, keeping the system out of PCI-DSS scope today.
- **No injection surface.** No raw SQL, `.extra()`, `os.system`, `subprocess`, `pickle`, `eval`, or `mark_safe` anywhere in the backend; the Django ORM is used throughout. `payments/pdf.py` uses ReportLab's `canvas.drawString`, which does **not** interpret markup (unlike `Paragraph`), so invoice fields cannot inject PDF markup — I checked this specifically rather than assuming.
- **Secrets hygiene in the repo is correct** — see **I-3**.
- **`SimpleJWT` rejects deactivated users** (`CHECK_USER_IS_ACTIVE` defaults on), so disabling a `User` does immediately invalidate their access tokens. Verified in the installed library; do not report this as a gap.

## Recommended fix order

1. **H-1** — one-line permission fix per viewset; largest risk reduction per unit of effort.
2. **H-5** + **L-5** — add the login throttle *and* move the cache to Redis together; the throttle is weak without it.
3. **H-2** — fail closed on `SECRET_KEY`; coordinate with the Azure App Setting before merging.
4. **H-3** — remove the write from `get_queryset` and make `get_user_role` deterministic; document the new Admin bootstrap.
5. **H-4** + **M-5** — same surface, fix together (restrict `destroy`, constrain `status`).
6. **M-1** — logout endpoint, then shorten the access-token lifetime (needs the 401 interceptor first).
7. **M-4**, **M-3**, **M-2**, **M-6**, then the LOW band.

## Areas needing further manual testing (runtime only)

These cannot be settled from source and must be checked against the live deployment:

- **Is `DJANGO_SECRET_KEY` actually set, and is it strong?** This decides whether **H-2** is a HIGH or an active CRITICAL. Check the Azure App Service Application Settings for `crm-booking-backend`.
- **Real `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, and `CSRF_TRUSTED_ORIGINS` values.** Source defaults are safe (empty / localhost) and no wildcard exists in code, but confirm no deploy variable sets `*`.
- **TLS at the Azure edge** — TLS 1.2+ enforced, valid public certificate, HTTP→HTTPS redirect (relates to **L-2**, **L-3**).
- **Is `DB_SSLMODE` actually `require` or stronger in production?** It defaults to `require` in code but is env-overridable to `disable`.
- **Is the backend container reachable only through the App Service front end?** Decides **L-3**.
- **Is `DJANGO_DEBUG` false in production?** If true, error pages leak stack traces and settings (A02/A10).
- **Strength of `EMAIL_HOST_PASSWORD` (Gmail App Password) and whether the Google Calendar refresh token is still valid.**
- **Number of Daphne workers**, which determines the real multiplier on every rate limit (**L-5**) and whether notifications are silently dropping (**I-5**).
