from django.urls import path,include
from rest_framework_simplejwt.views import TokenRefreshView,TokenObtainPairView

from .views import GoogleSignInView, TeamManagementViewSet
from rest_framework.routers import DefaultRouter


app_name = "accounts"
router = DefaultRouter()
router.register(r'team-roles', TeamManagementViewSet, basename='team-roles')

urlpatterns = [
    path("login/", TokenObtainPairView.as_view(), name="token-obtain-pair"), 
    path("google/", GoogleSignInView.as_view(), name="google-sign-in"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("", include(router.urls)),
]
