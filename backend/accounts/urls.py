from django.urls import path,include

from .views import (
    EmailOTPRequestView,
    EmailOTPVerifyView,
    GoogleSignInView,
    LogoutView,
    MFAConfirmView,
    MFASetupView,
    MFAStatusView,
    TeamManagementViewSet,
    ThrottledTokenObtainPairView,
    ThrottledTokenRefreshView,
)
from rest_framework.routers import DefaultRouter


app_name = "accounts"
router = DefaultRouter()
router.register(r'team-roles', TeamManagementViewSet, basename='team-roles')

urlpatterns = [
    path("login/", ThrottledTokenObtainPairView.as_view(), name="token-obtain-pair"),
    path("google/", GoogleSignInView.as_view(), name="google-sign-in"),
    path("otp/request/", EmailOTPRequestView.as_view(), name="otp-request"),
    path("otp/verify/", EmailOTPVerifyView.as_view(), name="otp-verify"),
    path("token/refresh/", ThrottledTokenRefreshView.as_view(), name="token-refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("mfa/status/", MFAStatusView.as_view(), name="mfa-status"),
    path("mfa/setup/", MFASetupView.as_view(), name="mfa-setup"),
    path("mfa/confirm/", MFAConfirmView.as_view(), name="mfa-confirm"),
    path("", include(router.urls)),
]
