from django.db.models.signals import post_save
from django.dispatch import receiver

from booking.models import Booking

from .services import BillingService, _bump_version
from .models import Invoice, Payment

BOOKING_TO_INVOICE_STATUS = {
    Booking.PaymentStatus.PENDING: Invoice.PaymentStatus.UNPAID,
    Booking.PaymentStatus.PAID: Invoice.PaymentStatus.PAID,
    Booking.PaymentStatus.REFUNDED: Invoice.PaymentStatus.REFUNDED,
}


@receiver(post_save, sender=Booking)
def create_invoice_for_new_booking(sender, instance, created, **kwargs):
    """Every booking automatically gets an UNPAID invoice — no more frontend fallback needed."""
    if created:
        BillingService.generate_invoice_for_booking(instance)
        return

    try:
        invoice = instance.invoice
    except Invoice.DoesNotExist:
        return

    update_fields = []

    if invoice.due_date != instance.booking_date:
        invoice.due_date = instance.booking_date
        update_fields.append("due_date")

    target_status = BOOKING_TO_INVOICE_STATUS.get(instance.payment_status)

    if target_status and invoice.status != target_status:
        # ✅ keep the Payment table in sync too, so revenue/refund/pending totals stay accurate
        # even when the status is changed directly from the Booking side (not via invoice pay/refund).
        if target_status == Invoice.PaymentStatus.PAID:
            if not invoice.payments.filter(status=Payment.PaymentStatus.PAID).exists():
                Payment.objects.create(
                    invoice=invoice,
                    amount=invoice.total_amount,
                    payment_method="CASH",
                    status=Payment.PaymentStatus.PAID,
                )
        elif target_status == Invoice.PaymentStatus.REFUNDED:
            latest_paid = invoice.payments.filter(status=Payment.PaymentStatus.PAID).order_by("-id").first()
            if latest_paid:
                latest_paid.status = Payment.PaymentStatus.REFUNDED
                latest_paid.save(update_fields=["status"])
            else:
                Payment.objects.create(
                    invoice=invoice,
                    amount=invoice.total_amount,
                    payment_method="CASH",
                    status=Payment.PaymentStatus.REFUNDED,
                )

        invoice.status = target_status
        update_fields.append("status")

    if update_fields:
        invoice.save(update_fields=update_fields)
        _bump_version(f"invoice_version_{instance.created_by_id}")
        _bump_version(f"payment_version_{instance.created_by_id}")