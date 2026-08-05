from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import DashboardSummaryView

app_name = "dashboard"

urlpatterns = [path("summary/", DashboardSummaryView.as_view(), name="dashboard-summary")]