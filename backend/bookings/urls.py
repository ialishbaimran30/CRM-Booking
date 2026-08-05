from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/clients/", include("clients.urls")),
    path("api/", include("booking.urls")),
    path("api/dashboard/", include("dashboard.urls")),
    path("api/resources/", include("resources.urls")),
    path("api/payments/", include("payments.urls")),
    path("api/notifications/", include("notifications.urls")),
    path("api/reports/", include("reports.urls")),
]
