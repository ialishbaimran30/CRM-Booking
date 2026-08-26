import secrets
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser
from django.core.validators import validate_email
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone


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


class EmailOTP(models.Model):
    """One-time passcode issued for passwordless email sign-in/sign-up."""

    MAX_ATTEMPTS = 5
    TTL_MINUTES = 10
    RESEND_COOLDOWN_SECONDS = 60

    email = models.EmailField(db_index=True)
    code_hash = models.CharField(max_length=128)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["email", "-created_at"])]

    def is_expired(self):
        return timezone.now() >= self.expires_at

    @classmethod
    def generate_for_email(cls, email):
        raw_code = f"{secrets.randbelow(1_000_000):06d}"
        instance = cls.objects.create(
            email=email,
            code_hash=make_password(raw_code),
            expires_at=timezone.now() + timedelta(minutes=cls.TTL_MINUTES),
        )
        return instance, raw_code

    def check_code(self, raw_code):
        return check_password(raw_code, self.code_hash)


class TeamRoleAssignment(models.Model):
    ROLE_CHOICES = [
        ('Admin', 'Admin'),
        ('Booking Manager', 'Booking Manager'),
    ]

    # Not globally unique: there are many Booking Manager rows (one per person
    # assigned), but exactly one Admin row — enforced by the constraint below.
    role_name = models.CharField(max_length=100, choices=ROLE_CHOICES)
    assigned_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_team_roles'
    )
    assigned_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['role_name'], condition=Q(role_name='Admin'), name='accounts_single_admin_seat'
            ),
            models.UniqueConstraint(
                fields=['role_name', 'assigned_user'],
                condition=Q(assigned_user__isnull=False),
                name='accounts_unique_role_per_user',
            ),
        ]

    def __str__(self):
        return f"{self.role_name} -> {self.assigned_user.email if self.assigned_user else 'Unassigned'}"


class TOTPDevice(models.Model):
    """A staff member's second factor (F-2). One per user — enrolling
    again replaces the existing (unconfirmed or confirmed) device, so a
    lost-device recovery flow is just "enroll again", gated by whichever
    of TOTP/recovery-code the user still has.

    The secret is stored in plaintext, matching common practice for TOTP
    devices (e.g. django-otp) — it must be readable to generate the
    expected code each login, unlike a password hash. Protected by normal
    database access controls, same as every other credential in this
    table's blast radius.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="totp_device")
    secret = models.CharField(max_length=64)
    confirmed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        status = "confirmed" if self.confirmed else "pending"
        return f"TOTP device for {self.user.email} ({status})"


class TOTPRecoveryCode(models.Model):
    """One-time-use recovery codes issued when a TOTPDevice is confirmed —
    hashed at rest (never recoverable, only re-issued by re-enrolling),
    for when the authenticator app/device is unavailable."""

    device = models.ForeignKey(TOTPDevice, on_delete=models.CASCADE, related_name="recovery_codes")
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Recovery code for {self.device.user.email} ({'used' if self.used_at else 'unused'})"