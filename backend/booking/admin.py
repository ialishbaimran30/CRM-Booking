from django.contrib import admin
from .models import Booking


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
