from django.core.validators import EmailValidator
from django.db import models

class Client(models.Model):
    """Represents a client in the CRM."""

    class ClientStatus(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"

    full_name = models.CharField(max_length=255)
    email = models.EmailField(max_length=255, unique=True)
    phone_number = models.CharField(max_length=20, blank=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=ClientStatus.choices, default=ClientStatus.ACTIVE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.full_name

    @classmethod
    def get_or_create_for_user(cls, user):
        """Resolve the Client record for an authenticated user's own account, matching by email."""
        client = cls.objects.filter(email__iexact=user.email).first()
        if client:
            return client
        return cls.objects.create(
            full_name=user.full_name or user.email.split("@")[0],
            email=user.email,
        )