"""Two related but distinct logging paths for SecurityFeatures.md F-1:

- `log_security_event` -> the `security` logger (settings.LOGGING), a
  structured stream for authentication/authorization *events*, meant to be
  shipped off-box and alerted on (F-9). Cheap, fire-and-forget.
- `record_audit_event` -> the `AuditLog` model (core/models.py), a
  persistent, queryable trail for privileged *business* actions. Must
  survive a restart and log rotation, so it's a DB row, not a log line.

Neither ever receives a password, OTP code, or JWT — callers only ever pass
identifiers (emails, ids) and business field values.
"""

import logging

security_logger = logging.getLogger("security")


def get_client_ip(request):
    """Best-effort source IP. Trusts X-Forwarded-For because Azure App
    Service (and any reverse proxy in front of this app) sets it — see
    SECURE_PROXY_SSL_HEADER in settings.py for the same trust assumption."""
    if request is None:
        return None
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_security_event(event, request, *, outcome, actor=None, extra=None):
    """Emit one structured `security` log line. Never raises — a logging
    failure must not break the request it's describing."""
    try:
        user = actor
        if user is None and request is not None:
            candidate = getattr(request, "user", None)
            user = candidate if candidate is not None and candidate.is_authenticated else None

        payload = {
            "event": event,
            "outcome": outcome,
            "actor_id": getattr(user, "id", None),
            "actor_email": getattr(user, "email", "") or "",
            "ip": get_client_ip(request),
            "path": getattr(request, "path", ""),
            "method": getattr(request, "method", ""),
        }
        if extra:
            payload.update(extra)
        security_logger.info(event, extra=payload)
    except Exception:
        security_logger.exception("Failed to emit security event log for event=%s", event)


def record_audit_event(*, actor, action, target=None, changes=None, request=None):
    """Write one AuditLog row for a privileged business action. Never
    raises — a broken audit write must not roll back the business action it
    describes; failure is itself logged to `security` so it isn't silent."""
    from .models import AuditLog  # local import: avoids a circular import at app-load time

    try:
        target_type = ""
        target_id = ""
        target_repr = ""
        if target is not None:
            target_type = type(target).__name__
            target_id = str(getattr(target, "pk", target))
            target_repr = str(target)[:255]

        AuditLog.objects.create(
            actor=actor if actor is not None and getattr(actor, "is_authenticated", False) else None,
            actor_email=getattr(actor, "email", "") or "",
            action=action,
            target_type=target_type,
            target_id=target_id,
            target_repr=target_repr,
            changes=changes or {},
            ip_address=get_client_ip(request),
        )
    except Exception:
        security_logger.exception("Failed to write AuditLog entry for action=%s", action)
