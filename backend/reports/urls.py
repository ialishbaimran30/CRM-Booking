from django.urls import path
from .views import DashboardSummaryAPIView, PeriodicReportAPIView

app_name = "reports"

urlpatterns = [
    path("dashboard/summary/", DashboardSummaryAPIView.as_view(), name="dashboard-summary"),
    path("periodic/", PeriodicReportAPIView.as_view(), name="periodic-report"),
]