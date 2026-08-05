from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView,TokenObtainPairView

from .views import GoogleSignInView

app_name = "accounts"

urlpatterns = [
    path("login/", TokenObtainPairView.as_view(), name="token-obtain-pair"), 
    path("google/", GoogleSignInView.as_view(), name="google-sign-in"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
]
