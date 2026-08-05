from rest_framework import serializers

from .models import Invoice, Payment


class PaymentSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="invoice.booking.client.full_name", read_only=True)
    service_name = serializers.CharField(source="invoice.booking.service_name", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id", "invoice", "amount", "status", "payment_method",
            "transaction_id", "refund_reason", "client_name", "service_name", "paid_at",
        ]
        read_only_fields = ["transaction_id", "paid_at"]


class InvoiceSerializer(serializers.ModelSerializer):
    payments = PaymentSerializer(many=True, read_only=True)
    client_id = serializers.IntegerField(source="booking.client.id", read_only=True)
    client_name = serializers.CharField(source="booking.client.full_name", read_only=True)
    service_name = serializers.CharField(source="booking.service_name", read_only=True)  # ✅ fix: booking.service -> booking.service_name
    is_overdue = serializers.BooleanField(read_only=True)
    latest_transaction_id = serializers.SerializerMethodField()
    paid_at = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            "id", "booking", "client_id", "client_name", "service_name",
            "invoice_number", "subtotal", "discount_amount", "coupon_code",
            "tax_amount", "total_amount", "status", "is_overdue",
            "issued_date", "due_date", "payments",
            "latest_transaction_id", "paid_at",
        ]
        read_only_fields = ["invoice_number", "total_amount", "status", "issued_date"]

    def get_latest_transaction_id(self, obj):
        payment = obj.payments.order_by("-id").first()
        return payment.transaction_id if payment else obj.invoice_number

    def get_paid_at(self, obj):
        return obj.booking.booking_date