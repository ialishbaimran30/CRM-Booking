from django.contrib.auth.models import AbstractUser
from django.core.validators import validate_email
from django.db import models
from django.db.models.functions import Lower


class User(AbstractUser):
    """Application user; can authenticate with password and/or Google."""

    email = models.EmailField(unique=True, validators=[validate_email])
    full_name = models.CharField(max_length=255, blank=True)
    google_subject = models.CharField(max_length=255, unique=True, null=True, blank=True)
    profile_picture_url = models.URLField(blank=True)
    email_verified = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique"),
        ]

    def __str__(self):
        return self.email
