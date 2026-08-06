import logging

from django.core.exceptions import ImproperlyConfigured
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import AuthenticatedUserSerializer, GoogleSignInSerializer
from .services import (
    GoogleAccountLinkError,
    GoogleTokenVerificationError,
    GoogleTokenVerificationUnavailable,
    authenticate_google_account,
    verify_google_id_token,
)
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import TeamRoleAssignment
from .serializers import TeamRoleSerializer, TeamUserListSerializer
from django.contrib.auth.models import User
from django.contrib.auth import get_user_model

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


class IsRoleOwnerOrReadOnly(permissions.BasePermission):
    """
    Enforces that only the user currently assigned to the role can modify (transfer) it.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        # Only allow if the authenticated user is the current owner of this role
        return obj.assigned_user == request.user



# ... (keep your GoogleSignInView and IsRoleOwnerOrReadOnly classes unchanged)

class TeamManagementViewSet(viewsets.ModelViewSet):
    queryset = TeamRoleAssignment.objects.all().order_by('id')
    serializer_class = TeamRoleSerializer
    permission_classes = [permissions.IsAuthenticated, IsRoleOwnerOrReadOnly]

    def get_queryset(self):
        default_roles = [
            'CRM Administrator',
            'Operations Manager',
            'Sales Manager',
            'Finance Manager',
            'Business Analyst'
        ]
        for role_name in default_roles:
            role_obj, created = TeamRoleAssignment.objects.get_or_create(role_name=role_name)
            
            # Auto-assign 'CRM Administrator' to the currently logged-in user if it's unassigned
            if role_name == 'CRM Administrator' and not role_obj.assigned_user:
                if self.request and self.request.user and self.request.user.is_authenticated:
                    role_obj.assigned_user = self.request.user
                    role_obj.save()
        return super().get_queryset()

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def available_users(self, request):
        User = get_user_model()
        users = User.objects.all().order_by('full_name')
        serializer = TeamUserListSerializer(users, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def me(self, request):
        serializer = AuthenticatedUserSerializer(request.user)
        return Response(serializer.data)