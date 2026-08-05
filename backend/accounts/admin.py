from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Google profile", {"fields": ("full_name", "google_subject", "profile_picture_url", "email_verified")} ),
    )
    list_display = ("email", "username", "full_name", "email_verified", "is_staff")
    search_fields = ("email", "username", "full_name", "google_subject")
