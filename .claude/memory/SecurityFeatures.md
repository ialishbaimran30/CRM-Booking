# SecurityFeatures.md — CRM-Booking Control-Gap Analysis

**Audit date:** 2026-08-25
**Auditor:** `security-auditor` agent, grounded in the `owasp-security` skill (ASVS 5.0 lens)
**Lens:** *What is not implemented, and should be?* — the paired vulnerability file is `.claude/memory/SecurityIssues.md`.

Every gap below was confirmed to exist **nowhere** in the codebase. Anything anchorable to a specific `file:line` is a finding, not a gap, and lives in `SecurityIssues.md` instead; where the two touch, this file cross-references by ID (`H-2`, `M-1`, …) rather than restating.

---

## How to use this file

- **IDs are stable.** `F-1`, `F-7`, etc. are safe to reference in later conversations ("build F-1 and F-6"). Never renumber them.
- **Mark, don't delete.** When a control is built, change `Status: OPEN` to `Status: FIXED 2026-09-01`, leaving the entry in place. Use `Status: ACCEPTED RISK <reason>` when the team decides the control is not warranted. This file is a living tracker.
- **EXPECTED / RECOMMENDED / MATURITY are priority bands, not severities.** EXPECTED means the Step-2 classification (client PII + financial records, ASVS L2) genuinely demands it. RECOMMENDED strengthens posture materially. MATURITY is for a system that has the basics covered.
- **Each entry names why *this* system needs it**, tied to a specific structural fact — not a generic checklist item. If that fact has changed, the gap may be stale.
- **Re-audit only when the system has moved materially.** A payment gateway landing, a second business/tenant, or a new authentication path would each change this analysis; building individual controls does not.

---

## System classification (carried forward from the audit's Step 2)

**Access model — hybrid.** Two onboarding paths coexist. The **client side is public self-serve**: `accounts/urls.py` exposes `otp/request/`, `otp/verify/`, and `google/` as `AllowAny`, so anyone can obtain an account with no staff role and is treated as a "Client" everywhere (`get_user_role` returns `None`). The **staff side is admin-provisioned**: `TeamRoleAssignment` rows are not self-assignable and are managed through `TeamManagementViewSet` gated by `IsAdmin`. The practical consequence that drives several gaps below: *any stranger with an email address is an authenticated principal in this system.*

**Actors and trust boundaries**, highest privilege first:
- **Admin** — exactly one seat, enforced by a DB constraint; full control including staff role assignment.
- **Booking Manager** — staff, multiple seats; operational access to bookings/clients/payments, not role management.
- **Client** — any authenticated user with no `TeamRoleAssignment` row; should reach only their own bookings, resolved by email match.
- **Anonymous** — OTP request/verify, Google sign-in, password login, token refresh.
- **Google Calendar service** — server-to-server via a stored encrypted refresh token, acting for the business account.
- **SMTP (Gmail)** — outbound only, credentials in `EMAIL_HOST_PASSWORD`.

The client/staff boundary is enforced **per-view**, not by a central gate — which is why a missed permission class is a direct access-control failure (see `H-1`).

**Data classes handled:**
- **Contact/PII** — `clients.Client` (full name, email, phone, address, city, country, free-text notes), `accounts.User` (email, full name, Google subject, profile picture URL).
- **Financial** — `payments.Invoice` (amounts, discounts, coupon codes, tax) and `payments.Payment` (amount, method incl. cash/card/bank transfer/JazzCash-EasyPaisa/online, transaction ID, refund reason). **No raw card PAN storage** — confirmed still true.
- **Authentication secrets** — `EmailOTP.code_hash` (hashed), JWT refresh tokens (blacklist app installed), and the Google OAuth refresh token for the business Calendar account (encrypted at rest, but see `M-2`).
- **No health, biometric, or government-ID data.**

**Tenancy:** single-tenant — one business, one CRM. No per-tenant isolation key exists to verify.

**Regulatory surface:** client PII plus financial transaction records imply general data-protection obligations. JazzCash/EasyPaisa payment methods and an `Asia/Karachi` timezone indicate a Pakistan-based business (Pakistan's PDPA framework), with GDPR/UK-GDPR-style duties if any client is EU/UK-based. These are **implied obligations requiring legal confirmation, not a compliance verdict.**

**Implied ASVS level: L2** — real client PII and financial records with staff-privileged write access, but not safety-critical, not a financial institution, not government infrastructure. L2 is "what most applications should target". L3's 92 additional requirements are not applied wholesale; individual L3 controls are cited only where a specific gap warrants it.

**Confidence and invitation to correct.** This classification is derived from the current `accounts`, `clients`, and `payments` models plus `PROJECT_TRACKER.md`. It was re-verified during this audit and still holds. If a payment gateway integration, a multi-business/franchise mode, or a minors-facing feature has landed since, say so — the first would add PCI-DSS scope, the second would introduce a tenancy-isolation requirement that does not exist today, and the third would add age-verification and parental-consent duties.

---

## Executive summary

Three gaps change this system's security posture more than anything else on the list.

**There is no security audit log — at all.** Not a partial one: no authentication events, no authorization failures, no record of who changed a role, voided an invoice, or deleted a client. `Payment.marked_by` is the single attribution field in the entire codebase. ASVS 5.0 places the whole of V16 at L2, so for an L2 system this is the largest single divergence from the target bar. It also means every finding in `SecurityIssues.md` is currently **undetectable in production** — if `H-1` or `H-5` were exploited tomorrow, nothing would record it.

**The Admin seat has no second factor and no recovery path.** One account controls role assignment for everyone, can refund invoices and apply discounts, and reaches the Admin-only dashboard and reports. It can sign in with a password over an endpoint that has no rate limiting (`H-5`), with no breached-password check and no MFA. There is simultaneously no documented break-glass procedure for when that single account is lost — and the *de facto* recovery path that exists today is the privilege-escalation bug `H-3`.

**There is no key-management story.** The Google Calendar encryption key is derived from `DJANGO_SECRET_KEY` (`M-2`), so no secret in this system can be rotated independently of any other, and no rotation runbook exists.

**Update 2026-08-26:** `F-1` is FIXED. `F-9` (alerting/off-box-shipping) is code-complete and tested but not yet production-verified — see that entry. The Admin MFA/recovery gap (`F-2`/`F-4`) and the key-management gap (`F-5`) are both still open.

**Update 2026-08-27:** `F-2`, `F-3`, `F-4`, and `F-6` are now FIXED — see each entry. `F-5` (secret/key-management runbook) remains the only open item in the EXPECTED band. RECOMMENDED and MATURITY items (`F-7`, `F-8`, `F-10`–`F-15`) are unchanged from the original audit.

**Update 2026-08-27 (full re-audit, same day):** every FIXED entry above was re-verified against the current code (all intact, 68/68 tests passing) and, where practical, live-tested rather than only read. `F-6` is downgraded to **PARTIALLY FIXED** — the throttle classes are correctly built, but a newly-verified finding (`SecurityIssues.md H-6`) shows they can be bypassed entirely via a spoofed `X-Forwarded-For` header. `F-2` gets a cross-reference to a newly-verified gap (`M-7`, MFA re-enrollment needs no proof of prior possession) rather than a status change, since the core login-time MFA check itself works correctly. No new items were added to this file's own GAPS list — both new findings are *implemented-but-wrong* (misconfiguration / missing re-auth step), which is `SecurityIssues.md`'s lens, not a *missing capability*.

| Band | Count |
|---|---|
| EXPECTED | 6 |
| RECOMMENDED | 6 |
| MATURITY | 3 |
| **Total** | **15** |

---

## Applicability note — domains assessed and ruled out

Assessed and found **not applicable** to this system, one line each:

- **Multi-tenancy isolation** — N/A, single-tenant (one business, one CRM); no tenant key exists to scope.
- **PCI-DSS cardholder-data controls** — N/A, no card PAN, CVV, or track data is stored; `payments` records method + amount + transaction ID only, and `PROJECT_TRACKER.md` confirms the payment provider is not yet integrated. **Re-assess when it lands** (see *Deliberate omissions*).
- **Minors' / age-verification protections** — N/A, no date-of-birth or age data is collected and nothing indicates a minors-facing service.
- **LLM Top 10 (2025) and Agentic AI ASI01–ASI10** — N/A, no LLM, agent, or RAG component exists anywhere in `backend/` or `frontend/src/` (grep for `openai|anthropic|generativeai|langchain|mistralai|cohere|ollama` matched nothing but the auditor's own agent definition).
- **WebRTC (ASVS V17)** — N/A, not used.
- **File upload security (ASVS V5)** — N/A, the application accepts no file uploads; the only binary artefact is a server-generated invoice PDF.
- **SAML/enterprise SSO federation** — N/A, no enterprise IdP; Google Sign-In is consumer OIDC and is handled under V10.

---

## GAPS

---

### EXPECTED

---

#### F-1 — Security audit logging and an audit trail for privileged actions
**Band:** EXPECTED · **ASVS 5.0:** 16.2.1, 16.2.2, 16.3.1, 16.3.2, 16.3.4, 16.4.1, 16.4.2 (all **L2**)
**Status: FIXED 2026-08-26** — all four "What to build" items shipped:
1. Structured JSON logging to stdout: `LOGGING` dict in `settings.py` + `core/logging.py::JSONFormatter` (JSON encoding is what satisfies 16.4.1 — a value can't inject a fake log line since it's escaped inside a JSON string).
2. `security` logger (`core/audit.py::log_security_event`) with explicit calls at: login success/failure (`accounts/serializers.py::LoggingTokenObtainPairSerializer`), token refresh (`accounts/views.py::ThrottledTokenRefreshView`), OTP request/verify outcomes, Google sign-in outcomes (all in `accounts/views.py`), and every DRF 403 via a custom exception handler (`core/exceptions.py`, wired in via `REST_FRAMEWORK["EXCEPTION_HANDLER"]` — covers every view at once, satisfying 16.3.2 in one place).
3. Persistent `AuditLog` model (`core/models.py`, migration `core/migrations/0001_initial.py`) for privileged actions: role assignment/removal (`accounts/views.py::TeamManagementViewSet`), invoice create/update/delete/pay/unpaid/refund (`payments/services.py::BillingService` + `payments/views.py::InvoiceViewSet`), client create/update/delete (`clients/views.py::ClientViewSet`), booking cancel/delete (`booking/views.py::BookingViewSet`). Read-only in Django admin via `core/admin.py`.
4. No secrets logged — login/OTP logging captures only the submitted identifier (email/username), never the password or OTP code; verified by `core/tests.py`'s `test_..._without_leaking_the_...` tests.

14 new tests in `core/tests.py` (26 total backend tests, all passing). **Update 2026-08-26:** shipping these logs off-box and alerting on them is `F-9` — code-complete and tested, not yet production-verified (see that entry).

**Why this system needs it.** ASVS 5.0 has **no L1 logging requirements** — the entire V16 chapter begins at L2, which is precisely the level this system is classified at. Beyond the standard: this is a CRM holding client PII and financial records where **staff hold broad write privileges by design** (any Booking Manager can edit any client and any invoice; the Admin can refund and discount). A privilege model that broad is only safe if it is *observable*, and right now it is not.

**Confirmed absent.** There is no logging framework configuration at all — `backend/bookings/settings.py` defines no `LOGGING` dict, so Django's defaults apply and nothing security-relevant is emitted. Application code uses `logger.exception(...)` only for operational failures (Calendar sync, email send, unexpected auth errors). Searching the backend finds **no** logging of: successful or failed authentication, authorization denials, OTP verification attempts, role assignment changes, invoice create/void/refund, client record edits or deletions, or booking cancellations. The single attribution field in the entire data model is `Payment.marked_by`. `TeamRoleAssignment` records `assigned_at` but never *who* assigned it.

**Risk in this system's terms.** If a **Booking Manager** exfiltrates the client list, edits an invoice, or escalates to Admin via `H-3`, there is no record that it happened, no way to establish when it started, and no way to scope the damage afterwards. If an **Anonymous** attacker runs credential stuffing against the unthrottled login endpoint (`H-5`), no failed-authentication events are recorded, so the attack is invisible both live and in retrospect. A client disputing a payment cannot be answered from an audit trail because none exists — and under `H-4` the record may have been deleted outright. This gap is what makes every other finding in the paired file undetectable.

**What to build.**
1. **A structured application log.** Add a `LOGGING` dict to `settings.py` emitting JSON to stdout (correct for a container on App Service, where stdout is collected). Include timestamp on a synchronised clock, actor user id, source IP, action, target object type and id, and outcome (16.2.1, 16.2.2).
2. **A dedicated `security` logger** with explicit event calls at: login success and failure (`TokenObtainPairView` subclass — you are creating one anyway for `H-5`), OTP request/verify outcomes, Google sign-in outcomes, every DRF `PermissionDenied` (via a custom exception handler, which covers 16.3.2 across all views at once), and token refresh.
3. **A persistent `AuditLog` model** for privileged business actions — role assignment changes, invoice create/update/void/refund, client create/update/delete, booking cancel/delete. A log line is enough for security events; business audit needs to be queryable and to survive log rotation. Record actor, action, target, before/after where meaningful, and timestamp. Write it from the service layer (`payments/services.py::BillingService` already centralises the invoice actions, which makes this cheap) rather than from each view.
4. **Never log secrets** — no OTP codes, no JWTs, no passwords (16.2.5), and encode log data to prevent log injection (16.4.1).

**Dependencies.** None blocking. Pairs naturally with `F-9` (shipping logs off-box and alerting on them) — a log nobody reads is not a detection control. The `AuditLog` model needs one migration. Doing this *before* the `SecurityIssues.md` fixes is defensible: it means you can tell whether anything was exploited before you closed the holes.

**Confidence.** High. Verified by absence of any `LOGGING` configuration and by reading every view and service module for security-event emission.

---

#### F-2 — Multi-factor authentication for the Admin seat
**Band:** EXPECTED · **ASVS 5.0:** 6.3.3 [L2] — "MFA, or a documented combination of single factors"
**Status: FIXED 2026-08-27** — TOTP-based second factor for all staff (Admin and Booking Manager, not Clients). `accounts/models.py::TOTPDevice`/`TOTPRecoveryCode`, service logic in `accounts/mfa.py`, enrollment endpoints `POST /api/accounts/mfa/setup/` + `/confirm/` (`accounts/views.py`), enforced at login in `accounts/serializers.py::LoggingTokenObtainPairSerializer` — staff with a confirmed device must submit `totp_code` or a one-time `recovery_code`, returned only once at enrollment (hashed at rest). A wrong/missing code returns a distinct `{"mfa_required": [...]}` shape so the frontend can prompt rather than show "invalid password," and also feeds the existing F-9 `alert_on_login_failure` rate-based alert. Not built: any frontend UI for enrollment or the login-time code prompt — this is a backend-only pass; the API contract is stable and documented above for whoever builds that next. Not built: a self-service "disable MFA" endpoint (deliberately — see the file's own reasoning that this would be new attack surface); today disabling requires deleting the `TOTPDevice` row directly, matching this codebase's existing break-glass pattern. **Two things found and live-verified in the 2026-08-27 re-audit, tracked separately rather than reopening this entry**: `SecurityIssues.md M-7` — re-enrolling MFA needs no proof of prior possession, so a stolen session can silently replace a confirmed device; and the login endpoint's TOTP-guessing rate limit inherits `H-6`'s `X-Forwarded-For` bypass (still bounded by 1-in-a-million odds per guess, so lower practical risk than password brute-forcing, but not actually rate-limited as designed).

**Why this system needs it.** The Admin is a **single seat enforced by a DB constraint** (`accounts_single_admin_seat`) that controls staff role assignment for everyone else, invoice refunds and discounts, and the Admin-only dashboard and reports modules. Concentrating that much authority in one account without a second factor makes that one credential the whole system's security boundary. ASVS 5.0 puts MFA at L2, and this system is classified L2.

**Confirmed absent.** There is no MFA implementation anywhere: no TOTP library in `backend/requirements.txt`, no `django-otp`, no WebAuthn, no second-factor model, no step-up challenge on any sensitive action. Three sign-in paths exist and **none** enforces a second factor for staff: `TokenObtainPairView` (password only), `GoogleSignInView`, and `EmailOTPVerifyView`.

A nuance worth recording so this is not over- or under-stated: the **email OTP path is single-factor, not MFA** — possession of the mailbox is the *only* factor, not a second one. And while **Google Sign-In inherits whatever MFA the user has on their Google account**, that protection is bypassed entirely by the password path: an Admin who also has a usable password can be attacked through `/api/accounts/login/` regardless of how well their Google account is protected.

**Risk in this system's terms.** An **Anonymous** attacker harvests the staff email list from the open `resources` endpoint (`H-1`), brute-forces the unthrottled login endpoint (`H-5`) with no breached-password check standing in the way (`F-3`), and on success holds the single Admin seat — able to assign themselves and others any role, read every client's PII, and refund or discount invoices. No second factor stands between the password and total compromise, and no log records the attempt (`F-1`).

**What to build.** Enforce a second factor for any user holding a `TeamRoleAssignment` — staff only; do not impose it on self-serve Clients, where it would be disproportionate.
- Simplest path that fits the existing architecture: **TOTP** via `django-otp` + `qrcode`, with enrolment required on first staff sign-in and verification required at token issuance. The existing `EmailOTP` model is *not* a good basis for this — email is a weak second factor and here it is already a primary one.
- Because the Admin seat is a single point of failure, ASVS's **L3 clause on 6.3.3** (one factor hardware-based and phishing-resistant, e.g. a FIDO2/WebAuthn key) is worth considering *for the Admin specifically*, even though this system is otherwise L2-targeted. This is the one place the higher bar is proportionate.
- Provide recovery codes at enrolment, and store them hashed — otherwise MFA becomes a lockout risk and feeds directly into `F-4`.

**Dependencies.** Requires `F-4` (break-glass recovery) to be designed alongside it, or enabling MFA on the single Admin seat *creates* an availability risk. Frontend work: an enrolment screen and a challenge step in the login flow. Consider disabling the password path for staff entirely and standardising on Google Sign-In with enforced Google MFA — a materially cheaper option worth evaluating before building TOTP.

**Confidence.** High. Verified by dependency list and by reading all three authentication views.

---

#### F-3 — Breached-password screening and a staff password policy
**Band:** EXPECTED · **ASVS 5.0:** 6.2.12 [L2] (breached-password set), 6.2.4 [L1] (top-3000 common passwords)
**Status: FIXED 2026-08-27** — `accounts/validators.py::PwnedPasswordValidator` checks new passwords against the HIBP Pwned Passwords range API via k-anonymity (only the first 5 hex chars of the SHA-1 hash ever leave the process); wired into `AUTH_PASSWORD_VALIDATORS`. Fails open (logged, not silent) if the API is unreachable — a third-party outage must not block every password change. `MinimumLengthValidator` raised from 8 to 12. Per ASVS 6.2.5/6.2.7/6.2.10, deliberately did **not** add composition rules or forced rotation. Same caveat as always: this only runs wherever Django already invokes `validate_password` (admin forms, `createsuperuser`, `changepassword`) — there is still no self-service password-change API endpoint in this app for it to guard.

**Why this system needs it.** Staff — including the Admin — authenticate with passwords through `TokenObtainPairView`. Those passwords guard client PII and financial records. ASVS puts breached-password checking at L2.

**Confirmed absent.** `settings.py:99-104` configures Django's four stock validators: `UserAttributeSimilarityValidator`, `MinimumLengthValidator`, `CommonPasswordValidator`, `NumericPasswordValidator`. There is no integration with a breached-password corpus (Have I Been Pwned's k-anonymity range API or a local Pwned Passwords set).

**Partial credit, stated precisely:** `CommonPasswordValidator` ships with a ~20,000-entry list, which **satisfies 6.2.4 [L1]** — do not report that as missing. `MinimumLengthValidator` defaults to 8 characters, which **meets 6.2.1 [L1]** but sits well below the 15 ASVS strongly recommends. The specific L2 gap is 6.2.12: no check against *breached* passwords, which is a different and far larger corpus than "common" ones.

A further gap worth noting: these validators run in Django's `set_password` flow (`createsuperuser`, admin password change). Because staff accounts are provisioned through Django admin and there is no self-service password-change endpoint in the API, the validators do apply — but nothing enforces a *stronger* policy for the single Admin than for anyone else.

**Risk in this system's terms.** An **Anonymous** attacker credential-stuffs the unthrottled login endpoint (`H-5`) with passwords from public breach corpora. Since no check prevents staff from choosing a password that already appears in a breach, and reuse across services is the norm, a single hit yields Booking Manager or Admin access.

**What to build.**
1. Add a custom `AUTH_PASSWORD_VALIDATORS` entry calling the **HIBP Pwned Passwords range API** with k-anonymity (send only the first 5 characters of the SHA-1 hash; the full password never leaves the process). Fail **closed** on API unavailability for staff-privileged accounts, or cache a local Bloom filter of the corpus to avoid the network dependency entirely.
2. Raise `MinimumLengthValidator` to 12–15 for all accounts.
3. Per ASVS 6.2.5 and 6.2.7, do **not** add composition rules and do **not** block paste or password managers — longer minimums plus breach screening is the modern guidance, and adding character-class rules would move *away* from the standard.
4. Per 6.2.10 [L2], do **not** introduce forced periodic rotation; rotate on compromise only.

**Dependencies.** Outbound HTTPS to `api.pwnedpasswords.com` unless using a local corpus. Existing staff passwords are not re-screened retroactively — screen at next change, or force a one-time reset for staff accounts when this ships.

**Confidence.** High. Verified by reading `AUTH_PASSWORD_VALIDATORS` and confirming no breach-check code or dependency exists.

---

#### F-4 — Break-glass recovery for the single Admin seat
**Band:** EXPECTED · **ASVS 5.0:** 6.3.x (authentication lifecycle), 8.2.1 (function-level access)
**Status: FIXED 2026-08-27** — `accounts/management/commands/transfer_admin_seat.py`, a general `--to <email> [--confirm]` command (dry-run preview by default), requiring server/shell access as its authorization gate — same shape as the superuser-claim precedent this app already used elsewhere. Always writes an `AuditLog` entry (`AuditLog.Action.ADMIN_SEAT_TRANSFERRED`) so a break-glass transfer is never silent. Full procedure documented in `backend/ADMIN_RECOVERY.md`. Distinct from the pre-existing `ensure_admin_seat` command, which is a narrow, single-hardcoded-email fixup tool, not a general recovery path — left untouched. Not built: changing `assigned_user` to `on_delete=PROTECT` (item 3 in this entry's original "what to build") — deliberately skipped, since `H-3`'s fix already removed the silent-auto-claim danger that made vacancy risky in the first place; revisit if that changes.

**Why this system needs it.** This gap is specific to this system's deliberate design, not a generic "have a recovery process" note. `accounts/models.py` enforces `accounts_single_admin_seat` — a `UniqueConstraint` permitting exactly **one** Admin row — and `TeamRoleSerializer.validate` actively refuses to create a second Admin ("transfer the existing Admin seat instead"). Meanwhile `assigned_user` uses `on_delete=SET_NULL`, so deleting the Admin's user account **vacates the seat rather than removing it**. The system therefore has exactly one holder of its highest privilege and no sanctioned way to replace them from inside the application.

**Confirmed absent.** There is no documented or coded break-glass path. No recovery runbook exists in `PROJECT_TRACKER.md`, `GOOGLE_AUTH_SETUP.md`, or `GOOGLE_CALENDAR_SETUP.md`. No management command performs an audited Admin transfer. No emergency second-Admin mechanism, no time-boxed elevation, no dual-control approval.

What exists instead is worse than nothing: the **de facto** recovery path today is the privilege-escalation defect `H-3` — `TeamManagementViewSet.get_queryset` silently hands the vacant seat to whichever staff member next loads the team roster. That is an accidental control, it is unaudited, and `H-3`'s remediation **removes it**. So closing `H-3` without building `F-4` leaves the system with no recovery path at all. These two must be planned together.

**Risk in this system's terms.** The Admin leaves the company, loses their credentials, has their account compromised and disabled, or (once `F-2` ships) loses their MFA device. The business is then unable to assign staff roles, refund invoices, apply discounts, or view reports — indefinitely — and recovery requires direct database or Django-admin-superuser access, which is itself an unaudited backdoor. Conversely, if the seat is left vacant and `H-3` is unfixed, any Booking Manager silently becomes Admin.

**What to build.**
1. **A documented, audited transfer procedure.** A management command (e.g. `python manage.py transfer_admin_seat --to <email>`) runnable only with server access, which reassigns the seat and writes an `AuditLog` entry (`F-1`). Server access is a reasonable authorisation gate for break-glass; silence is not.
2. **Preserve the superuser path deliberately.** `_provision_client_if_unstaffed` (`accounts/views.py:40-63`) already claims a vacant Admin seat for `user.is_superuser` — that *is* a sound break-glass primitive because `createsuperuser` requires shell access. Document it as the official recovery route, and make it emit an audit event so a silent claim becomes a recorded one.
3. **Prevent silent vacancy.** Consider changing `assigned_user` to `on_delete=PROTECT` so an Admin account cannot be deleted while holding the seat, forcing an explicit transfer first.
4. **Write the runbook** — who is authorised to invoke recovery, what approval is required, and what is logged.

**Dependencies.** Design jointly with `H-3`'s fix and with `F-2` (MFA introduces device-loss as a new lockout mode; recovery codes mitigate but do not eliminate it). Item 3 requires a migration. Depends on `F-1` for the audit trail to write into.

**Confidence.** High. Verified from the model constraints, the serializer's transfer-only rule, the `SET_NULL` behaviour, and the absence of any recovery command or documentation.

---

#### F-5 — Secret and encryption-key management with a rotation path
**Band:** EXPECTED · **ASVS 5.0:** 11.4.1 (approved key management), 14.x (data protection at rest)
**Status: OPEN**

**Why this system needs it.** The system holds a long-lived Google OAuth **refresh token for the business account** (encrypted at rest), a Gmail App Password, database credentials, and a JWT signing key. `M-2` establishes that the Calendar encryption key is derived as `sha256(DJANGO_SECRET_KEY)` and `H-2` that `SECRET_KEY` itself falls back to a committed default. Both are code-level findings recorded in `SecurityIssues.md`. **The gap recorded here is the missing capability around them:** there is no rotation mechanism, no runbook, and no inventory — so even after `M-2` and `H-2` are fixed, nobody can answer "how do we rotate this after a suspected leak?"

**Confirmed absent.** No key-management tooling exists: no Azure Key Vault integration (secrets are plain App Service Application Settings), no `MultiFernet` or any versioned-key construct, no re-encryption management command, no documented rotation procedure in any of the three setup docs, and no key-inventory record of what secrets exist, who holds them, or when they were last changed.

**Risk in this system's terms.** A developer laptop with a copy of `.env` is stolen; a contractor with production access departs; a database backup leaks. The correct response is to rotate — but rotating `DJANGO_SECRET_KEY` today simultaneously invalidates every session and JWT (forcing all users to re-authenticate) **and** renders the stored Google Calendar refresh token permanently undecryptable, silently stopping Calendar sync (`google_calendar.py` degrades to an error string while bookings continue to succeed). Faced with that, the realistic organisational outcome is that nothing gets rotated and the exposed key stays in service indefinitely.

**What to build.**
1. **Separate the secrets** — implement `M-2` first so the Calendar key has an independent lifecycle. This is the prerequisite for everything else here.
2. **Make rotation non-destructive.** Use `MultiFernet` with a comma-separated key list (first key encrypts, all keys decrypt), plus a `rotate_calendar_key` management command that re-encrypts the stored credential onto the new key. Same pattern for `SIMPLE_JWT["SIGNING_KEY"]` — set it explicitly to its own secret rather than inheriting `SECRET_KEY`, so JWT signing can rotate without touching session integrity.
3. **Centralise storage.** Move secrets to Azure Key Vault with App Service references, so values are versioned, access-controlled, and auditable rather than pasted into portal settings.
4. **Write the runbook and inventory** — every secret, its purpose, its owner, its rotation cadence, and the exact steps and blast radius of rotating it. This is the deliverable that actually closes the gap.

**Dependencies.** `M-2` is a hard prerequisite. Adding `CALENDAR_TOKEN_KEY` (and optionally a distinct JWT signing key) means new entries in `backend/.env.example` and new Azure Application Settings. Existing encrypted rows need a re-encryption migration or a one-time Calendar reconnect — see `M-2`'s ripple-effects note.

**Confidence.** High. Verified by absence of any key-management dependency, rotation command, or documentation.

---

#### F-6 — Baseline anti-automation across the API
**Band:** EXPECTED · **ASVS 5.0:** 6.3.1 [L1] (anti-automation), 2.2.1 (business-expectation validation)
**Status: PARTIALLY FIXED — downgraded from FIXED on 2026-08-27's re-audit.** `DEFAULT_THROTTLE_CLASSES` now includes `AnonRateThrottle`/`UserRateThrottle` alongside the existing `ScopedRateThrottle`, so every endpoint has a baseline limit (anon 60/min, user 300/min) instead of only the three previously-scoped auth views. Added dedicated scopes for the expensive endpoints named in the original remediation: `booking_write` (20/hour, booking create/update), `pdf` (30/hour, `InvoiceViewSet.pdf`), `report` (60/hour, both `reports` views and `DashboardSummaryView`). Same caveat as `H-5`: **`L-5` (shared cache) is still open**, so these limits are per-process, not cluster-wide, until that lands. **More severe than that caveat suggests**: a full re-audit live-verified `SecurityIssues.md H-6` — every anonymous-context throttle this entry built (and `H-5`'s login throttle) can be bypassed *entirely*, regardless of `L-5`'s status, by spoofing the `X-Forwarded-For` header per request, because `REST_FRAMEWORK["NUM_PROXIES"]` was never set. The structure is built correctly; it does not yet actually stop an anonymous attacker. See `H-6` for the fix (`NUM_PROXIES = 1`) and live-verification evidence.

**Why this system needs it.** The client side is **public self-serve**, so every authenticated-user endpoint is reachable by anyone willing to register. Several of those endpoints are expensive or drive outbound side effects: booking creation writes to Google Calendar and sends email, `InvoiceViewSet.pdf` renders a PDF per request, the reports endpoints load and aggregate every invoice in Python (`I-6`), and booking updates trigger waitlist email broadcasts to third parties (`M-5`).

**Confirmed absent.** `settings.py:143-144` sets `DEFAULT_THROTTLE_CLASSES` to `ScopedRateThrottle` **only**, with rates defined for exactly three scopes: `google_auth`, `otp_request`, `otp_verify`. `ScopedRateThrottle` is inert on any view that does not declare a `throttle_scope`. There is **no `AnonRateThrottle` and no `UserRateThrottle` baseline anywhere**, so every endpoint in the system other than those three auth views is entirely unthrottled.

This gap is the general capability. The specific, anchorable instance — the password login endpoint having no scope — is `H-5` in `SecurityIssues.md`; do not double-count them. Note also that `L-5` (per-process `LocMemCache`) and `L-4` (`cache.clear()` flushing throttle state) undermine whatever throttling does exist, so this gap is not fully closed by configuration alone.

**Risk in this system's terms.** A **Client** — trivially self-registered — scripts booking creation and cancellation to drive waitlist email broadcasts at volume, exhausting the Gmail SMTP quota and damaging the business domain's sending reputation; or hammers the PDF endpoint (once `H-1`-class access issues elsewhere are considered) to exhaust CPU. An **Anonymous** attacker enumerates or floods any unauthenticated surface without resistance. Nothing records any of it (`F-1`).

**What to build.**
1. Add baseline throttles so the default is protective rather than permissive:

```python
"DEFAULT_THROTTLE_CLASSES": (
    "rest_framework.throttling.ScopedRateThrottle",
    "rest_framework.throttling.AnonRateThrottle",
    "rest_framework.throttling.UserRateThrottle",
),
"DEFAULT_THROTTLE_RATES": {
    "anon": "60/min", "user": "300/min",
    "google_auth": "10/min", "otp_request": "5/min", "otp_verify": "10/min",
    "login": "5/min",              # see H-5
    "booking_write": "20/hour",    # see M-5
    "pdf": "30/hour", "report": "60/hour",
},
```

2. Add targeted `throttle_scope` attributes to the expensive endpoints: booking create/update, `InvoiceViewSet.pdf`, and the two `reports` views.
3. Consider a per-recipient cap on waitlist notification emails so no single actor can drive unbounded outbound mail to third parties.

**Dependencies.** **Requires `L-5`** (a shared cache backend) to be meaningful — with `LocMemCache`, limits multiply by worker count and reset on restart. Fix the cache backend first or the throttles are decorative. Tune the numbers against real traffic; the values above are starting points, not measurements.

**Confidence.** High. Verified by reading the throttle configuration and confirming, view by view, that only three declare a `throttle_scope`.

---

### RECOMMENDED

---

#### F-7 — Account lifecycle controls and session visibility
**Band:** RECOMMENDED · **ASVS 5.0:** 7.4.2 (terminate sessions on account disable), 6.x (account lifecycle)
**Status: OPEN**

**Why this system needs it.** Identity here is **email-anchored**: `Client.get_or_create_for_user` resolves a user's client record by `email__iexact`, and `BookingViewSet.get_queryset` scopes a Client's bookings the same way. Email is therefore not merely a contact field — it is the authorization key for client data isolation.

**Confirmed absent.** There is no account-management surface at all: no email-change endpoint (and so no re-verification flow), no self-service account deletion or deactivation, no "sign out everywhere", and no session/device inventory. `AuthenticatedUserSerializer` is entirely read-only.

**Precise scoping — two things that ARE handled, so do not report them as gaps.** First, SimpleJWT's `CHECK_USER_IS_ACTIVE` defaults to `True`, so setting `User.is_active = False` **does** immediately invalidate that user's access tokens — verified in the installed library. Second, the frontend does clear tokens from `localStorage` on logout, satisfying ASVS 14.3.1. The real session gap is the absence of server-side revocation on logout, which is `M-1` in `SecurityIssues.md`.

**Risk in this system's terms.** Because no email-change path exists, the email-as-authorization-key design is currently safe — but the moment one is added without re-verification, a **Client** could change their address to a target's and gain access to that person's bookings through the email match. Recording this now is what prevents that mistake. Separately, users have no way to see or terminate their other sessions, so a user who suspects compromise has no self-service response, and staff offboarding has no "revoke everything" action beyond deactivating the account.

**What to build.** If an email-change feature is ever added, require verification of the **new** address before the change takes effect and notify the old address — and re-resolve or migrate the `Client` link explicitly rather than letting the email match silently re-point. Add a session/device list backed by the `token_blacklist` outstanding-token tables (already installed), with a "revoke this session" and "sign out everywhere" action. Add an admin-facing "terminate all sessions for this user" control for offboarding. Provide account deletion/deactivation with a defined data outcome (ties to `F-8`).

**Dependencies.** Builds on `M-1` (which introduces the blacklist-on-logout mechanism these features extend). Needs `F-1` to log lifecycle events.

**Confidence.** High for the absence; the email-change risk is explicitly conditional on a feature that does not exist yet, and is recorded as a design constraint rather than a present vulnerability.

---

#### F-8 — Data retention, deletion, and privacy rights handling
**Band:** RECOMMENDED · **ASVS 5.0:** 14.x (data protection); driven primarily by the regulatory surface in the classification above
**Status: OPEN**

**Why this system needs it.** The system stores identifiable client PII — full name, email, phone, address, city, country, and **free-text notes** — alongside financial transaction records, indefinitely. Free-text notes are the highest-risk field because they routinely accumulate unstructured sensitive detail nobody planned for. The classification's implied obligations (Pakistan PDPA; GDPR/UK-GDPR if any client is EU/UK-based) generally require defined retention periods and a means to honour erasure and access requests.

**Confirmed absent.** No retention policy is expressed anywhere in code or documentation. No data is ever purged: `Booking`, `Invoice`, `Payment`, and `Client` rows persist forever. There is no data-export endpoint (subject access) and no erasure/anonymisation routine. The only bounded-growth logic in the system is the opportunistic `EmailOTP` cleanup in `accounts/services.py:170-172` — good practice, and the only example of it.

**Risk in this system's terms.** Unbounded PII accumulation enlarges the blast radius of every other finding in the paired file: a breach exposes years of client records rather than a working set. A client exercising an erasure right cannot be served without manual `DELETE` statements — and naive deletion is unsafe here, because `Booking.client` is `on_delete=CASCADE`, so deleting a `Client` silently destroys their bookings and (through `H-4`'s cascade path) the associated financial records the business is separately obliged to retain. Erasure and financial retention are in direct tension and need a deliberate design.

**What to build.** Define retention periods per data class, distinguishing operational PII (deletable on request) from financial records (typically retained for a statutory period). Implement **anonymisation rather than deletion** for clients with financial history: null the PII fields, keep the invoice rows and their amounts, and replace the identity with a stable pseudonym so reporting stays intact. Add a client data-export endpoint (Admin-gated) for subject access requests. Add a scheduled purge for data past its retention period. Document the policy and confirm the retention periods with legal counsel — the classification's regulatory note is an implied obligation, not a verdict.

**Dependencies.** Requires legal input on retention periods before implementation. Interacts with `H-4` — resolve how invoices survive booking/client removal as part of that fix. Anonymisation needs a migration if pseudonym fields are added.

**Confidence.** Medium-high on the technical absence (verified); the regulatory framing requires legal confirmation as stated in the classification.

---

#### F-9 — Detection, alerting, and off-box log storage
**Band:** RECOMMENDED · **ASVS 5.0:** 16.4.2 (logs protected from modification), 16.4.3 [L2] (logs shipped to a separate system for analysis and alerting)
**Status: CODE COMPLETE — pending Azure configuration + production verification.** Correction: this was briefly marked FIXED on 2026-08-26 before any of it had actually run against real infrastructure — that was premature and has been reverted. All code is written, tested (35/35 backend tests, including 23 exercising this feature directly), and committed, but nothing here becomes a working control until an operator configures the Azure resources below and someone confirms, in production, that logs land in Log Analytics and alert emails actually arrive. Do not re-mark FIXED without that evidence.

**What shipped.**
1. **Off-box log shipping**, opt-in via `AZURE_LOG_ANALYTICS_CONNECTION_STRING`: `bookings/settings.py` conditionally adds an `azure` handler (class `core.logging.AzureLogHandler`) to the `security` and `django` loggers. **A real bug was found and fixed while building this**: `opencensus-ext-azure` 1.1.15's `AzureLogHandler.createLock()` sets `self.lock = None` without overriding `handle()`, so the stock class crashes (`TypeError: 'NoneType' object does not support the context manager protocol`) on the very first log call — reproduced by hand. `core/logging.py::AzureLogHandler` wraps it with a subclass that restores a real `threading.RLock()`. A second issue found the same way: the SDK's own "statsbeat" self-telemetry makes a synchronous network call during handler construction, adding ~9 seconds to every process boot; `settings.py` sets `APPLICATIONINSIGHTS_STATSBEAT_DISABLED_ALL=true` to kill that (Microsoft's own documented opt-out, not app telemetry — this doesn't disable the actual log shipping). With both fixes, verified by hand: Django boots (~4-5s one-time cost when the connection string is set, versus 13s unpatched), a real log call reaches the SDK's transmit pipeline without crashing or hanging, and no non-daemon thread is left behind. **What is not, and cannot be, verified from this repo**: actual delivery into a real Azure Log Analytics workspace, since no live Azure resource or connection string exists here — that requires an operator to provision one, set the env var, and confirm data lands. Package declared in `requirements.txt` (`opencensus-ext-azure>=1.1,<2.0`).
2. **Alerting**, fully built and tested without needing any external service: `core/alerting.py` routes the exact conditions the audit named — failed-login rate per account/IP (`accounts/serializers.py`), every authorization denial (`core/exceptions.py`), every `TeamRoleAssignment` change (`accounts/views.py`), every invoice void/refund (`payments/services.py`, `payments/views.py` — deliberately not pay/unpaid, which are routine), and booking-cancellation spikes (`booking/views.py`) — to `settings.ADMINS` via Django's own `mail_admins`. `settings.SECURITY_ALERT_EMAILS` (comma-separated) populates `ADMINS`; empty by default, so alerting is a deliberate per-deployment opt-in with a real owner once set. Each alert is deduplicated per condition for 15 minutes (a burst sends one email, not one per event) using the same cache-based counter pattern the rest of the codebase already uses (`_bump_version`) — which means, like `H-5`'s throttle, this is only accurate cluster-wide once **`L-5`** (shared cache) is fixed; today each worker process counts independently.

23 new tests in `core/tests.py` (35 total backend tests, all passing), including hand-verified reproductions of both `opencensus-ext-azure` bugs above and integration tests confirming the `TeamManagementViewSet` call sites actually trigger an alert end to end, not just that the alerting functions work in isolation.

**What's still a deployment step, not code**: provisioning the actual Azure Log Analytics workspace, setting `AZURE_LOG_ANALYTICS_CONNECTION_STRING` and `SECURITY_ALERT_EMAILS` as real App Service settings, and confirming a simulated failed-login burst produces both a visible Log Analytics entry and a delivered email — the audit's own bar ("an untested alert is not a control") can only be fully cleared once those two env vars point at real infrastructure. Alert *thresholds* were followed as specified except one deliberate deviation: "any authorization denial for a staff-only route" fires on every 403 in this app (every 403 here already comes from a staff/admin gate) but is deduped per (actor, view) for 15 minutes rather than literally per-event, to avoid an ordinary buggy client script flooding the inbox — the underlying `security` log still records every single denial regardless.

**Why this system needs it.** `F-1` produces the signal; this gap is the absence of anywhere to send it and anyone to tell. ASVS 16.4.3 explicitly requires logs to reach a logically separate system — a log that lives only on the compromised host is evidence an attacker can edit or erase.

**Confirmed absent.** No log aggregation is configured, no Azure Application Insights or Log Analytics integration exists in the Dockerfile, the workflows, or settings. No alerting rules, no anomaly detection, no on-call path, and no monitoring of authentication failure rates or authorization denials.

**Risk in this system's terms.** Even after `F-1` ships, an **Anonymous** attacker brute-forcing `H-5` or a **Booking Manager** escalating via `H-3` produces log lines nobody ever reads. Detection latency is effectively unbounded — breaches would be discovered by a client complaint or a payment dispute rather than by the system. Container logs are also ephemeral: on App Service they are lost on restart unless shipped.

**What to build.** Ship structured logs to Azure Log Analytics (or equivalent) with retention outliving any single container instance. Define alert rules on the events `F-1` emits: failed-authentication rate per IP and per account, any authorization denial for a staff-only route, any `TeamRoleAssignment` change, any invoice void or refund, and any spike in booking cancellations (which drive outbound waitlist mail per `M-5`). Route alerts to a real destination with an owner. Confirm the pipeline works by running a simulated failed-login burst and verifying the alert fires end to end — an untested alert is not a control.

**Dependencies.** **Requires `F-1`** — there is nothing to ship until security events are emitted. Build them in that order.

**Confidence.** High. Verified by absence of any monitoring configuration in settings, Dockerfile, or CI.

---

#### F-10 — Automated dependency and secret scanning in CI
**Band:** RECOMMENDED · **ASVS 5.0:** 15.x · **OWASP:** A03:2025
**Status: OPEN**

**Why this system needs it.** The backend installs unpinned version ranges at build time (`M-6`), and the project has two automated deployment pipelines that ship to production on push to `development`. Without a scanning gate, a vulnerable or malicious dependency reaches production automatically, and a committed secret is not caught before it is published.

**Confirmed absent.** Neither `.github/workflows/development_crm-booking-backend.yml` nor `azure-static-web-apps-*.yml` contains any security step: no `pip-audit`, no `npm audit`, no Dependabot configuration (no `.github/dependabot.yml` exists), no CodeQL or SAST, and no secret scanning. Neither workflow runs tests either — and there are effectively none to run (`F-12`).

**Risk in this system's terms.** A CVE in `cryptography`, `Django`, `reportlab`, or any transitive dependency is adopted silently on the next build (`M-6`), and nobody learns of it until it is exploited. A future accidental commit of `backend/.env` — currently correctly ignored, per `I-3` — would flow straight to a build with nothing to catch it.

**What to build.** Add a `security` job to both workflows running `pip-audit --requirement requirements.lock` (after `M-6` lands) and `npm audit --omit=dev`, failing the build on high-severity findings. Enable **Dependabot** with a `.github/dependabot.yml` covering both `pip` and `npm` ecosystems so upgrades arrive as reviewable PRs rather than silent build-time drift. Enable **GitHub secret scanning** and **push protection** on the repository. Add **CodeQL** for Python and JavaScript. Pin all actions to commit SHAs and add least-privilege `permissions:` blocks while you are editing these files (`L-6`).

**Dependencies.** `pip-audit` is most useful once `M-6`'s lock file exists — pinning without scanning freezes vulnerabilities in place, so these two are complements and should ship close together.

**Confidence.** High. Both workflow files read in full; no dependabot config present.

---

#### F-11 — Backup and recovery for the production database
**Band:** RECOMMENDED · **ASVS 5.0:** 14.x (data protection); resilience
**Status: OPEN**

**Why this system needs it.** The PostgreSQL database is the sole store of all client PII, every booking, and every invoice and payment record — the business's operational and financial history. `H-4` demonstrates that a Client can already permanently destroy financial records through the application itself, and there is no soft delete anywhere in the schema.

**Confirmed absent.** No backup configuration, schedule, retention policy, restore procedure, or documented RPO/RTO exists in the repository. The `Dockerfile` explicitly and correctly defers migrations to a separate step, but no operational documentation accompanies it. Whether Azure-managed automated backups are enabled on the database is not determinable from the codebase and must be confirmed in the portal.

**Risk in this system's terms.** Accidental or malicious data destruction — via `H-4`, via a mistaken bulk `DELETE`, via ransomware, or via a botched migration — is unrecoverable if no verified backup exists. Note also that `db.sqlite3` is the automatic fallback whenever `DB_NAME` is unset (`settings.py:83-97`): a deployment that loses its database environment variables would silently start writing to an ephemeral container-local SQLite file, appearing healthy while accumulating data that vanishes on restart. That failure mode is invisible without monitoring (`F-9`).

**What to build.** Confirm and document Azure Database for PostgreSQL automated backups with point-in-time restore, an explicit retention period, and geo-redundancy appropriate to the business. Encrypt backups at rest and restrict who can read them — a backup is a full copy of all client PII and inherits its sensitivity. **Test the restore path and record how long it takes**; an untested backup is not a backup. Define and document RPO/RTO. Consider making the SQLite fallback refuse to activate when `DJANGO_DEBUG` is false, so a missing `DB_NAME` fails loudly rather than silently.

**Dependencies.** Primarily an infrastructure task rather than a code change, except the SQLite-fallback guard. Coordinate retention with `F-8`, since backups extend the effective lifetime of data an erasure request was meant to remove.

**Confidence.** Medium — the absence of *documentation and code-level guards* is verified; Azure-side backup configuration cannot be determined from the repository and must be checked in the portal.

---

#### F-12 — Automated security regression testing
**Band:** RECOMMENDED · **ASVS 5.0:** 15.x (secure coding and architecture)
**Status: OPEN**

**Why this system needs it.** Authorization here is **per-view and uncentralised** — the structural fact that produced `H-1`, where one app simply omitted its permission class and nothing caught it. In an architecture where every new viewset is an opportunity to repeat that mistake, tests are the only mechanism that prevents recurrence.

**Confirmed absent.** Test coverage is essentially nil: `backend/accounts/tests.py` is 54 lines (`GoogleSignInViewTests`), `backend/dashboard/tests.py` is 3 lines, and `booking`, `clients`, `payments`, `reports`, `resources`, `notifications`, and `core` are all **1-line stubs**. Neither CI workflow runs `manage.py test` at all. There is no frontend test suite in the pipeline.

**Risk in this system's terms.** Every fix listed in `SecurityIssues.md` can silently regress. Worse, the *next* viewset added to this codebase will not be checked for a permission class by anything, so `H-1` recurs by default rather than by accident.

**What to build.** Start with an authorization matrix test — the highest-value security test this codebase could have. Parametrise over (actor × endpoint × method) for the four actors (Anonymous, Client, Booking Manager, Admin) and assert the expected status for every registered DRF route. Drive it from the router registry so **a newly added viewset appears in the matrix automatically** and fails until someone declares its intended access. That single test would have caught `H-1` on the day it was written. Then add regression tests for each fixed finding — the `Verification` section of every entry in `SecurityIssues.md` is written to be directly translatable into one. Add `python manage.py test` to the backend workflow as a required gate.

**Dependencies.** None blocking. Most valuable built alongside the `SecurityIssues.md` fixes so each fix ships with its regression test rather than being retrofitted.

**Confidence.** High. Verified by line-counting every `tests.py` and reading both workflows.

---

### MATURITY

---

#### F-13 — Software Bill of Materials (SBOM)
**Band:** MATURITY · **ASVS 5.0:** 15.x · **OWASP:** A03:2025
**Status: OPEN**

No SBOM is generated for either the Python or npm dependency tree. Without one, answering "are we affected by this newly disclosed CVE?" requires manual inspection of a dependency set that is not even pinned (`M-6`). Generate CycloneDX SBOMs in CI (`cyclonedx-py` and `@cyclonedx/cyclonedx-npm`) and retain them as build artefacts alongside the image tag, so any deployed version can be queried retrospectively. Build after `M-6` (lock file) and `F-10` (scanning), which together make an SBOM actionable rather than decorative.
**Confidence:** High.

---

#### F-14 — Application-level encryption for the most sensitive PII at rest
**Band:** MATURITY · **ASVS 5.0:** 14.x
**Status: OPEN**

Client PII — including the free-text `notes` field, which accumulates unstructured sensitive detail — is stored in plaintext columns, protected only by whatever transparent disk encryption Azure provides. That defends against physical media theft but not against a leaked backup, an over-privileged read replica, or SQL-injection-class access (none currently exists — no raw SQL anywhere — but the control is defence-in-depth against future regressions). Consider field-level encryption for `Client.notes`, `phone_number`, and `address`. Weigh the real cost honestly: encrypted columns cannot be searched or filtered, and `ClientViewSet` currently exposes `search_fields` over `full_name`, `email`, and `phone_number` — encrypting `phone_number` breaks that search. This is genuinely a maturity item; correct key management (`F-5`) is a hard prerequisite, since field encryption with an unrotatable key derived from `SECRET_KEY` would repeat `M-2`'s mistake at larger scale.
**Confidence:** High on absence; the trade-off is real and this may reasonably be declined.

---

#### F-15 — Documented incident response plan
**Band:** MATURITY · **ASVS 5.0:** 16.x · **OWASP:** A09:2025
**Status: OPEN**

No incident response plan, runbook, or breach-notification procedure exists. Given the system holds client PII subject to data-protection obligations that typically carry statutory notification deadlines, discovering a breach without a prepared plan means improvising under time pressure. Write a short plan covering: who is notified and in what order, how to revoke credentials and sessions in an emergency (depends on `M-1` and `F-7` existing), how to preserve evidence before remediating, how to determine breach scope from audit logs (`F-1`), and the notification obligations and deadlines confirmed with legal counsel. Two pages that exist beat twenty that do not. Depends on `F-1` and `F-9` for the forensic capability the plan assumes.
**Confidence:** High.

---

## Suggested build order

Sequenced by dependency and by risk reduction per unit of effort. Note that the `SecurityIssues.md` HIGH findings should generally be fixed first — but **F-1 is the arguable exception**, since building it before closing the holes tells you whether anything was already exploited.

1. **F-1 — audit logging.** Everything else in detection depends on it, and it is the largest single divergence from the L2 bar. Build it first, ideally before the `SecurityIssues.md` fixes land.
2. **F-6 — baseline throttling** (with `L-5`, the shared cache, as its prerequisite). Cheap, and it closes the abuse surface that `H-5` and `M-5` both sit on.
3. **F-4 — Admin break-glass recovery.** Must land **with or before** `H-3`'s fix, which removes the accidental recovery path the system relies on today. Do not close `H-3` without this.
4. **F-2 — MFA for staff**, designed jointly with `F-4`. Evaluate "enforce Google Sign-In for staff and disable the password path" first — it may deliver most of the benefit at a fraction of the cost.
5. **F-3 — breached-password screening.** Small, self-contained, and directly reduces the `H-5` attack's success rate.
6. **F-5 — key management**, once `M-2` has separated the Calendar key. The runbook is the deliverable.
7. **F-10 + F-12 — CI scanning and the authorization-matrix test.** Together these stop `H-1`-class regressions and silent dependency drift.
8. **F-9 — alerting**, once `F-1` produces signal worth routing.
9. **F-11 — verified backups**, and **F-7 / F-8** as the account-lifecycle and privacy work is scoped.
10. **F-13, F-14, F-15** — maturity items, once the above are in place.

---

## Deliberate omissions

Controls a reader might reasonably expect to find here, and why they are not recommended for this system today:

- **PCI-DSS cardholder-data controls** — omitted. No card PAN, CVV, or track data is stored; `payments` records payment *method*, amount, and a transaction ID only. `PROJECT_TRACKER.md` states the payment provider is not yet integrated ("Payment provider later integrate hoga"). Recommending PCI-DSS controls now would be disproportionate. **Re-assess the moment a gateway lands** — if card data ever touches this system, the classification changes materially and this file needs revisiting in full. Strongly prefer a hosted/redirect integration that keeps card data out of scope entirely.
- **Multi-tenant isolation controls** — omitted. Single-tenant by design: one business, one CRM. There is no tenant identifier to scope queries by, and manufacturing one would add complexity without reducing risk.
- **Minors' protections / age verification / parental consent** — omitted. No date-of-birth or age data is collected and nothing indicates a minors-facing service.
- **LLM and agentic AI controls** — omitted. No LLM, agent, or RAG component exists; assessed and confirmed by repository-wide grep.
- **Forced periodic password rotation** — deliberately omitted, and should be actively avoided. ASVS 6.2.10 [L2] requires passwords stay valid until compromised or user-rotated; scheduled expiry degrades password quality and contradicts the standard.
- **Password composition rules** (mandatory character classes) — deliberately omitted per ASVS 6.2.5. Length plus breach screening (`F-3`) is the current guidance; composition rules would move away from the standard, not toward it.
- **CAPTCHA on the client sign-up flow** — not recommended as a first move. Proper rate limiting (`F-6`) plus the existing OTP email-verification requirement already bound automated account creation, and a CAPTCHA adds friction to the public self-serve path that is this product's core flow. Revisit only if `F-1`'s logs show real abuse.
- **Web Application Firewall** — not listed as a gap. It would be compensating control for `H-1` and `H-5` rather than a fix; fix the application first. Reasonable to add later at the Azure Front Door layer as defence-in-depth.
