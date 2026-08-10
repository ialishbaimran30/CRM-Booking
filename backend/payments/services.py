from decimal import Decimal
from uuid import uuid4

from django.core.cache import cache

from .models import Invoice, Payment


def _bump_version(key):
    version = cache.get(key, 1)
    cache.set(key, version + 1)


class BillingService:
    """Service layer to handle billing calculations, invoice generation, and payment/refund actions."""

    @staticmethod
    def generate_invoice_for_booking(booking, discount_amount=Decimal("0.00"), tax_amount=Decimal("0.00")):
        subtotal = booking.price
        total_amount = max((subtotal - discount_amount) + tax_amount, Decimal("0.00"))
        invoice_number = f"INV-{uuid4().hex[:8].upper()}"

        invoice, _ = Invoice.objects.update_or_create(
            booking=booking,
            defaults={
                "invoice_number": invoice_number,
                "subtotal": subtotal,
                "discount_amount": discount_amount,
                "tax_amount": tax_amount,
                "total_amount": total_amount,
                "due_date": booking.booking_date,  # ✅ overdue check ke liye base
            },
        )
        return invoice

    @staticmethod
    def mark_invoice_paid(invoice, *, payment_method, discount_amount=None, coupon_code="", marked_by=None):
        """Applies an optional discount, then records one full payment (no partial payments)."""
        if invoice.status == Invoice.PaymentStatus.PAID:
            raise ValueError("This invoice is already paid.")
        if invoice.status == Invoice.PaymentStatus.REFUNDED:
            raise ValueError("A refunded invoice cannot be marked as paid.")

        if discount_amount is not None:
            invoice.discount_amount = Decimal(str(discount_amount))
            invoice.coupon_code = coupon_code or ""
            invoice.total_amount = max(
                invoice.subtotal - invoice.discount_amount + invoice.tax_amount, Decimal("0.00")
            )
            invoice.save(update_fields=["discount_amount", "coupon_code", "total_amount"])

        payment = Payment.objects.create(
            invoice=invoice,
            amount=invoice.total_amount,
            payment_method=payment_method,
            status=Payment.PaymentStatus.PAID,
            marked_by=marked_by,
        )
        invoice.status = Invoice.PaymentStatus.PAID
        invoice.save(update_fields=["status"])

        # ✅ keep the booking's payment_status in sync
        booking = invoice.booking
        booking.payment_status = booking.PaymentStatus.PAID
        booking.save(update_fields=["payment_status"])

        user_id = booking.created_by_id
        _bump_version(f"invoice_version_{user_id}")
        _bump_version(f"payment_version_{user_id}")
        _bump_version("booking_version_global")
        return payment

    @staticmethod
    def mark_invoice_unpaid(invoice):
        """Reverses a paid invoice back to unpaid (distinct from a refund — no refund reason recorded)."""
        if invoice.status == Invoice.PaymentStatus.UNPAID:
            raise ValueError("This invoice is already unpaid.")
        if invoice.status == Invoice.PaymentStatus.REFUNDED:
            raise ValueError("A refunded invoice cannot be marked as unpaid.")

        latest_payment = invoice.payments.filter(status=Payment.PaymentStatus.PAID).order_by("-id").first()
        if latest_payment:
            latest_payment.delete()

        invoice.status = Invoice.PaymentStatus.UNPAID
        invoice.save(update_fields=["status"])

        # keep the booking's payment_status in sync
        booking = invoice.booking
        booking.payment_status = booking.PaymentStatus.PENDING
        booking.save(update_fields=["payment_status"])

        user_id = booking.created_by_id
        _bump_version(f"invoice_version_{user_id}")
        _bump_version(f"payment_version_{user_id}")
        _bump_version("booking_version_global")
        return invoice

    @staticmethod
    def refund_invoice(invoice, *, reason="", marked_by=None):
        if invoice.status != Invoice.PaymentStatus.PAID:
            raise ValueError("Only a paid invoice can be refunded.")

        latest_payment = invoice.payments.filter(status=Payment.PaymentStatus.PAID).order_by("-id").first()
        if latest_payment:
            latest_payment.status = Payment.PaymentStatus.REFUNDED
            latest_payment.refund_reason = reason
            latest_payment.marked_by = marked_by
            latest_payment.save(update_fields=["status", "refund_reason", "marked_by"])

        invoice.status = Invoice.PaymentStatus.REFUNDED
        invoice.save(update_fields=["status"])

        # ✅ keep the booking's payment_status in sync
        booking = invoice.booking
        booking.payment_status = booking.PaymentStatus.REFUNDED
        booking.save(update_fields=["payment_status"])

        user_id = booking.created_by_id
        _bump_version(f"invoice_version_{user_id}")
        _bump_version(f"payment_version_{user_id}")
        _bump_version("booking_version_global")
        return invoice