from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from .models import Booking, GoogleCalendarCredential, Service, Waitlist


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "hourly_rate", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "description")


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        "service_name",
        "client",
        "booking_date",
        "start_time",
        "status",
        "payment_status",
        "calendar_sync_status",
        "created_by",
    )
    list_filter = ("status", "payment_status", "calendar_sync_status", "booking_date")
    search_fields = ("client__full_name", "service_name")
    autocomplete_fields = ["client", "created_by"]


@admin.register(Waitlist)
class WaitlistAdmin(admin.ModelAdmin):
    list_display = ("client", "booking_date", "start_time", "end_time", "notified_at", "created_at")
    list_filter = ("booking_date",)
    search_fields = ("client__full_name", "client__email")
    autocomplete_fields = ["client"]


@admin.register(GoogleCalendarCredential)
class GoogleCalendarCredentialAdmin(admin.ModelAdmin):
    """Read-only view of the business Calendar connection — the refresh
    token itself is never displayed. Use the connect link to (re)authorize."""

    list_display = ("connected_email", "calendar_id", "connected_by", "connected_at", "connect_link")
    readonly_fields = ("calendar_id", "connected_email", "connected_by", "connected_at", "updated_at", "connect_link")
    fields = readonly_fields

    def connect_link(self, obj):
        return format_html('<a href="{}">Connect / Reconnect</a>', reverse("google_calendar_connect"))
    connect_link.short_description = "Authorize"

    def has_add_permission(self, request):
        # Connecting happens exclusively through the OAuth flow.
        return False
