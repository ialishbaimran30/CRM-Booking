import logging

from django.core.exceptions import ImproperlyConfigured
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import (
    AuthenticatedUserSerializer,
    EmailOTPRequestSerializer,
    EmailOTPVerifySerializer,
    GoogleSignInSerializer,
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

    A Django superuser is a distinct, backend-only concept (it only controls
    /admin/ access) and is never itself read as a React role — but someone
    who already holds that trust and signs into the CRM with no
    TeamRoleAssignment yet is an operator waiting to claim the (usually
    already-provisioned-but-unassigned) Admin seat, never a Client. Claiming
    it here — instead of falling through to Client — is what actually fixes
    a Django superuser being resolved as Client; TeamRoleAssignment remains
    the sole source of truth the frontend reads.
    """
    if get_user_role(user) is not None:
        return
    if user.is_superuser:
        admin_seat = TeamRoleAssignment.objects.filter(role_name="Admin", assigned_user__isnull=True).first()
        if admin_seat:
            admin_seat.assigned_user = user
            admin_seat.save(update_fields=["assigned_user"])
            return
    Client.get_or_create_for_user(user)

logger = logging.getLogger(__name__)


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
            return Response(
                {"detail": "Google ID token is invalid, expired, revoked, or unverified."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except GoogleTokenVerificationUnavailable:
            return Response(
                {"detail": "Google token verification is temporarily unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except GoogleAccountLinkError:
            return Response(
                {"detail": "This email is already linked to another Google account."},
                status=status.HTTP_409_CONFLICT,
            )
        except ImproperlyConfigured:
            logger.exception("Google sign-in is not configured.")
            return Response({"detail": "Authentication service is not configured."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception:
            logger.exception("Unexpected Google sign-in failure.")
            return Response({"detail": "Unable to complete sign-in."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        _provision_client_if_unstaffed(user)
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
            return Response(
                {
                    "detail": "Please wait before requesting another code.",
                    "retry_after": exc.retry_after_seconds,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        except Exception:
            logger.exception("Failed to send OTP email.")
            return Response(
                {"detail": "Unable to send verification code."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

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
            return Response(
                {"detail": "Code not found or expired. Please request a new one."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except OtpLockedError:
            return Response(
                {"detail": "Too many incorrect attempts. Please request a new code."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        except OtpInvalidError as exc:
            return Response(
                {"detail": "Incorrect code.", "attempts_remaining": exc.attempts_remaining},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            logger.exception("Unexpected OTP verification failure.")
            return Response({"detail": "Unable to complete sign-in."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        _provision_client_if_unstaffed(user)
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
        # Bootstrap the single Admin seat only — Booking Manager is now a
        # dynamic list the Admin builds explicitly (create/remove), not a
        # fixed placeholder row.
        admin_role, _ = TeamRoleAssignment.objects.get_or_create(role_name='Admin')
        if not admin_role.assigned_user and self.request and self.request.user and self.request.user.is_authenticated:
            admin_role.assigned_user = self.request.user
            admin_role.save()
        return super().get_queryset()

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