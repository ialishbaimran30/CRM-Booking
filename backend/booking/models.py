from django.db import models
from django.conf import settings
from clients.models import Client


class Service(models.Model):
    """An Admin-defined, bookable service with an hourly rate. The single
    source of truth for pricing — Booking.rate_snapshot is copied from this
    at booking time so later rate changes never retroactively alter past
    bookings."""

    name = models.CharField(max_length=255, unique=True)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} (${self.hourly_rate}/hr)"


class Booking(models.Model):
    """Represents a booking for a client."""

    class BookingStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        CONFIRMED = "CONFIRMED", "Confirmed"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    class PaymentStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"
        REFUNDED = "REFUNDED", "Refunded"

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="bookings")
    service = models.ForeignKey(
        Service, on_delete=models.SET_NULL, null=True, blank=True, related_name="bookings"
    )
    # Denormalized display copy of service.name at booking time — kept so
    # existing search/display code (invoices, reports) doesn't need a join,
    # and so it still reads sensibly if the Service is later renamed/removed.
    service_name = models.CharField(max_length=255)
    booking_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    status = models.CharField(
        max_length=20, choices=BookingStatus.choices, default=BookingStatus.PENDING
    )
    notes = models.TextField(blank=True)
    # The final, backend-calculated total price (duration_hours * rate_snapshot
    # when a Service is used). Never trust a client-supplied value for this.
    price = models.DecimalField(max_digits=10, decimal_places=2)
    # The service's hourly rate captured at booking time — a permanent
    # snapshot so later Service.hourly_rate edits never change this booking's price.
    rate_snapshot = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookings"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # DB-level backstop against two active bookings racing for the same
            # slot (the standard hourly grid always shares identical start
            # times, so this closes the concurrent-double-booking window that
            # a plain serializer-level check can't).
            models.UniqueConstraint(
                fields=["booking_date", "start_time"],
                condition=models.Q(status__in=["PENDING", "CONFIRMED"]),
                name="unique_active_booking_slot",
            )
        ]

    def __str__(self):
        return f"{self.service_name} for {self.client.full_name} on {self.booking_date}"


class Waitlist(models.Model):
    """A client waiting to be notified when a specific booking slot frees up."""

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="waitlist_entries")
    booking_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["client", "booking_date", "start_time", "end_time"],
                name="unique_waitlist_entry_per_client_slot",
            )
        ]

    def __str__(self):
        return f"{self.client.full_name} waiting for {self.booking_date} {self.start_time}"
