from django.conf import settings
from django.db import models
from django.utils import timezone

from booking.models import Booking  # ⚠️ pehle "booking" (galat app name) tha — fix kar diya


class Invoice(models.Model):
    """Represents an invoice generated for a booking."""

    class PaymentStatus(models.TextChoices):
        UNPAID = "UNPAID", "Unpaid"
        PARTIALLY_PAID = "PARTIALLY_PAID", "Partially Paid"
        PAID = "PAID", "Paid"
        REFUNDED = "REFUNDED", "Refunded"

    booking = models.OneToOneField(
        Booking, on_delete=models.CASCADE, related_name="invoice"
    )
    invoice_number = models.CharField(max_length=50, unique=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    coupon_code = models.CharField(max_length=50, blank=True)  # ✅ naya field
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=30, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID
    )
    issued_date = models.DateTimeField(auto_now_add=True)
    due_date = models.DateField(null=True, blank=True)

    @property
    def is_overdue(self):
        """True if the invoice is still unpaid/partial and its due date has passed."""
        return (
            self.status in (self.PaymentStatus.UNPAID, self.PaymentStatus.PARTIALLY_PAID)
            and self.due_date is not None
            and self.due_date < timezone.now().date()
        )

    def __str__(self):
        return f"Invoice #{self.invoice_number} - {self.status}"


class Payment(models.Model):
    """Tracks individual payments made against invoices."""

    class PaymentMethod(models.TextChoices):
        CASH = "CASH", "Cash"
        CREDIT_CARD = "CREDIT_CARD", "Credit Card"
        BANK_TRANSFER = "BANK_TRANSFER", "Bank Transfer"
        JAZZCASH = "JAZZCASH", "JazzCash / EasyPaisa"
        ONLINE = "ONLINE", "Online Gateway"

    class PaymentStatus(models.TextChoices):
        PAID = "PAID", "Paid"
        REFUNDED = "REFUNDED", "Refunded"

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=30, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    transaction_id = models.CharField(max_length=255, blank=True, null=True)
    refund_reason = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PAID)
    paid_at = models.DateTimeField(null=True, blank=True)
    # Who performed the mark-paid/refund action (Admin or Booking Manager) — an audit trail.
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    def save(self, *args, **kwargs):
        if not self.transaction_id:
            year = timezone.now().year
            last_payment = Payment.objects.filter(transaction_id__startswith=f"TXN-{year}").order_by("-id").first()
            if last_payment and last_payment.transaction_id:
                try:
                    new_num = int(last_payment.transaction_id.split("-")[-1]) + 1
                except ValueError:
                    new_num = 1
            else:
                new_num = 1
            self.transaction_id = f"TXN-{year}-{new_num:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Payment of {self.amount} for Invoice #{self.invoice.invoice_number}"