from django.contrib import admin
from .models import Booking, Service, Waitlist


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
        "created_by",
    )
    list_filter = ("status", "payment_status", "booking_date")
    search_fields = ("client__full_name", "service_name")
    autocomplete_fields = ["client", "created_by"]


@admin.register(Waitlist)
class WaitlistAdmin(admin.ModelAdmin):
    list_display = ("client", "booking_date", "start_time", "end_time", "notified_at", "created_at")
    list_filter = ("booking_date",)
    search_fields = ("client__full_name", "client__email")
    autocomplete_fields = ["client"]
