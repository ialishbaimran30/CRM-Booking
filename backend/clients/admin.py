from django.contrib import admin
from .models import Client


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "email",
        "phone_number",
        "status",
        "created_at",
    )
    list_filter = ("status", "city", "country")
    search_fields = ("full_name", "email", "phone_number")