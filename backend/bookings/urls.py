from django.contrib import admin
from django.urls import include, path
from booking.admin_calendar_views import google_calendar_callback, google_calendar_connect

urlpatterns = [
    path("admin/", admin.site.urls),
    path("admin-tools/google-calendar/connect/", google_calendar_connect, name="google_calendar_connect"),
    path("admin-tools/google-calendar/callback/", google_calendar_callback, name="google_calendar_callback"),
    path("api/accounts/", include("accounts.urls")),
    path("api/auth/", include("accounts.urls")),
    path("api/clients/", include("clients.urls")),
    path("api/", include("booking.urls")),
    path("api/dashboard/", include("dashboard.urls")),
    path("api/resources/", include("resources.urls")),
    path("api/payments/", include("payments.urls")),
    path("api/notifications/", include("notifications.urls")),
    path("api/reports/", include("reports.urls")),
]
