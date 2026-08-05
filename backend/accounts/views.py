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
