from rest_framework.views import exception_handler as drf_default_exception_handler

from .alerting import alert_on_authorization_denied
from .audit import log_security_event


def logging_exception_handler(exc, context):
    """Wraps DRF's default exception handler to log every authorization
    denial (403) in one place, covering every view at once — SecurityFeatures.md
    F-1 point 2 ("every DRF PermissionDenied, via a custom exception handler").
    401s are not logged here: those are covered per-endpoint by the
    login/OTP/Google views themselves, which can log the attempted identity.
    """
    response = drf_default_exception_handler(exc, context)

    if response is not None and response.status_code == 403:
        request = context.get("request")
        view = context.get("view")
        view_name = view.__class__.__name__ if view else ""
        log_security_event(
            "authorization_denied",
            request,
            outcome="denied",
            extra={"view": view_name},
        )
        actor = getattr(request, "user", None)
        actor_email = getattr(actor, "email", "") if actor is not None and actor.is_authenticated else ""
        alert_on_authorization_denied(actor_email, view_name, getattr(request, "path", ""))

    return response
