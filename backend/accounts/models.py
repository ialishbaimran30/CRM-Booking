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

class TeamRoleAssignment(models.Model):
    ROLE_CHOICES = [
        ('CRM Administrator', 'CRM Administrator'),
        ('Operations Manager', 'Operations Manager'),
        ('Sales Manager', 'Sales Manager'),
        ('Finance Manager', 'Finance Manager'),
        ('Business Analyst', 'Business Analyst'),
    ]

    role_name = models.CharField(max_length=100, choices=ROLE_CHOICES, unique=True)
    assigned_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_team_roles'
    )
    assigned_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.role_name} -> {self.assigned_user.email if self.assigned_user else 'Unassigned'}"