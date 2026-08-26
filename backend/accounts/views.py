import logging

from django.core.exceptions import ImproperlyConfigured
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .serializers import (
    AuthenticatedUserSerializer,
    EmailOTPRequestSerializer,
    EmailOTPVerifySerializer,
    GoogleSignInSerializer,
    LoggingTokenObtainPairSerializer,
)
from .services import (
    GoogleAccountLinkError,
    GoogleTokenVerificationError,
    GoogleTokenVerificationUnavailable,
    OtpCooldownError,
    OtpInvalidError,
    OtpLockedError,
    OtpNotFoundError,
    authenticate_google_account,
    request_email_otp,
    verify_email_otp,
    verify_google_id_token,
)
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from clients.models import Client
from core.alerting import alert_on_login_failure, alert_on_role_change
from core.audit import get_client_ip, log_security_event, record_audit_event
from core.models import AuditLog
from .models import TeamRoleAssignment
from .permissions import IsAdmin, IsAdminOrReadOnly, IsStaffMember, get_user_role
from .serializers import TeamRoleSerializer, TeamUserListSerializer
from django.contrib.auth.models import User
from django.contrib.auth import get_user_model


def _provision_client_if_unstaffed(user):
    """Backend-driven role determination (single source of truth): a freshly
    authenticated user with no Staff Role is a Client — ensure their Client
    profile exists immediately, so the frontend can route them straight into
    the Client Portal without ever asking them to pick a role.

    Role assignment is never automatic on login, for anyone, superuser or
    not — a Django superuser only controls /admin/ access and is a distinct,
    backend-only concept from the CRM's Admin/Booking Manager/Client role.
    The Admin seat must always be assigned explicitly (directly in the
    database, or via the Team Management screen once someone already holds
    it) — never auto-claimed by whoever happens to sign in first.
    TeamRoleAssignment remains the sole source of truth the frontend reads.
    """
    if get_user_role(user) is not None:
        return
    Client.get_or_create_for_user(user)

logger = logging.getLogger(__name__)


class ThrottledTokenObtainPairView(TokenObtainPairView):
    """Password login, rate-limited — the stock view has no throttle at all.
    Logging of each attempt happens in LoggingTokenObtainPairSerializer."""

    serializer_class = LoggingTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"


class ThrottledTokenRefreshView(TokenRefreshView):
    """Token refresh, rate-limited for the same reason as login above."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "token_refresh"

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        outcome = "success" if response.status_code == 200 else "failure"
        log_security_event("token_refresh", request, outcome=outcome)
        return response


class GoogleSignInView(APIView):
    """Accept a Google ID token and exchange it for application JWTs."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "google_auth"

    def post(self, request):
        serializer = GoogleSignInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            identity = verify_google_id_token(serializer.validated_data["id_token"])
            user, created = authenticate_google_account(identity)
        except GoogleTokenVerificationError:
            log_security_event("google_sign_in", request, outcome="failure", extra={"reason": "invalid_token"})
            return Response(
                {"detail": "Google ID token is invalid, expired, revoked, or unverified."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except GoogleTokenVerificationUnavailable:
            log_security_event("google_sign_in", request, outcome="failure", extra={"reason": "verification_unavailable"})
            return Response(
                {"detail": "Google token verification is temporarily unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except GoogleAccountLinkError:
            log_security_event("google_sign_in", request, outcome="failure", extra={"reason": "account_link_conflict"})
            return Response(
                {"detail": "This email is already linked to another Google account."},
                status=status.HTTP_409_CONFLICT,
            )
        except ImproperlyConfigured:
            logger.exception("Google sign-in is not configured.")
            log_security_event("google_sign_in", request, outcome="failure", extra={"reason": "not_configured"})
            return Response({"detail": "Authentication service is not configured."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception:
            logger.exception("Unexpected Google sign-in failure.")
            log_security_event("google_sign_in", request, outcome="failure", extra={"reason": "unexpected_error"})
            return Response({"detail": "Unable to complete sign-in."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        _provision_client_if_unstaffed(user)
        log_security_event("google_sign_in", request, outcome="success", actor=user, extra={"created_account": created})
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": AuthenticatedUserSerializer(user).data,
                "created": created,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class EmailOTPRequestView(APIView):
    """Send a one-time passcode to the given email address."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "otp_request"

    def post(self, request):
        serializer = EmailOTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        try:
            request_email_otp(email)
        except OtpCooldownError as exc:
            log_security_event("otp_request", request, outcome="throttled", extra={"email": email})
            return Response(
                {
                    "detail": "Please wait before requesting another code.",
                    "retry_after": exc.retry_after_seconds,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        except Exception:
            logger.exception("Failed to send OTP email.")
            log_security_event("otp_request", request, outcome="failure", extra={"email": email})
            return Response(
                {"detail": "Unable to send verification code."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        log_security_event("otp_request", request, outcome="success", extra={"email": email})
        return Response({"detail": "Verification code sent.", "email": email}, status=status.HTTP_200_OK)


class EmailOTPVerifyView(APIView):
    """Verify a submitted OTP and exchange it for application JWTs."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "otp_verify"

    def post(self, request):
        serializer = EmailOTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        code = serializer.validated_data["code"]

        try:
            user, created = verify_email_otp(email, code)
        except OtpNotFoundError:
            log_security_event("otp_verify", request, outcome="failure", extra={"email": email, "reason": "not_found_or_expired"})
            alert_on_login_failure(email, get_client_ip(request))
            return Response(
                {"detail": "Code not found or expired. Please request a new one."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except OtpLockedError:
            log_security_event("otp_verify", request, outcome="locked", extra={"email": email})
            return Response(
                {"detail": "Too many incorrect attempts. Please request a new code."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        except OtpInvalidError as exc:
            log_security_event("otp_verify", request, outcome="failure", extra={"email": email, "reason": "incorrect_code"})
            alert_on_login_failure(email, get_client_ip(request))
            return Response(
                {"detail": "Incorrect code.", "attempts_remaining": exc.attempts_remaining},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            logger.exception("Unexpected OTP verification failure.")
            log_security_event("otp_verify", request, outcome="failure", extra={"email": email, "reason": "unexpected_error"})
            return Response({"detail": "Unable to complete sign-in."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        _provision_client_if_unstaffed(user)
        log_security_event("otp_verify", request, outcome="success", actor=user, extra={"email": email, "created_account": created})
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": AuthenticatedUserSerializer(user).data,
                "created": created,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class TeamManagementViewSet(viewsets.ModelViewSet):
    queryset = TeamRoleAssignment.objects.all().order_by('role_name', 'id')
    serializer_class = TeamRoleSerializer
    # Only Staff (Admin or Booking Manager) may see the team roster at all;
    # of those, only the current Admin may create/transfer/assign/remove entries.
    permission_classes = [permissions.IsAuthenticated, IsStaffMember, IsAdminOrReadOnly]

    def get_queryset(self):
        # Bootstrap the single Admin seat row only, so it always exists to be
        # explicitly assigned later — Booking Manager is a dynamic list the
        # Admin builds explicitly (create/remove), not a fixed placeholder
        # row. Assignment itself is never automatic: whoever happens to load
        # this endpoint first must never silently become Admin.
        TeamRoleAssignment.objects.get_or_create(role_name='Admin')
        return super().get_queryset()

    def _role_changes(self, instance):
        return {
            "role_name": instance.role_name,
            "assigned_user_email": instance.assigned_user.email if instance.assigned_user else None,
        }

    def perform_create(self, serializer):
        instance = serializer.save()
        changes = self._role_changes(instance)
        record_audit_event(
            actor=self.request.user, action=AuditLog.Action.ROLE_ASSIGNED,
            target=instance, changes=changes, request=self.request,
        )
        alert_on_role_change(AuditLog.Action.ROLE_ASSIGNED, self.request.user.email, changes)

    def perform_update(self, serializer):
        before = self._role_changes(serializer.instance)
        instance = serializer.save()
        changes = {"before": before, "after": self._role_changes(instance)}
        record_audit_event(
            actor=self.request.user, action=AuditLog.Action.ROLE_ASSIGNED, target=instance,
            changes=changes, request=self.request,
        )
        alert_on_role_change(AuditLog.Action.ROLE_ASSIGNED, self.request.user.email, changes)

    def perform_destroy(self, instance):
        changes = self._role_changes(instance)
        record_audit_event(
            actor=self.request.user, action=AuditLog.Action.ROLE_REMOVED, target=instance,
            changes=changes, request=self.request,
        )
        alert_on_role_change(AuditLog.Action.ROLE_REMOVED, self.request.user.email, changes)
        instance.delete()

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated, IsAdmin])
    def available_users(self, request):
        User = get_user_model()
        # Only users with no existing Staff Role can be assigned as a new Booking Manager.
        users = User.objects.exclude(assigned_team_roles__isnull=False).order_by('full_name')
        serializer = TeamUserListSerializer(users, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def me(self, request):
        serializer = AuthenticatedUserSerializer(request.user)
        return Response(serializer.data)