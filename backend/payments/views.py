from django.core.cache import cache
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from accounts.permissions import IsAdmin, IsStaffMember, is_admin
from .models import Invoice, Payment
from .serializers import InvoiceSerializer, PaymentSerializer
from .services import BillingService


def _bump_version(key):
    version = cache.get(key, 1)
    cache.set(key, version + 1)


class InvoiceViewSet(viewsets.ModelViewSet):
    # Payments is a Staff-only module (Admin or Booking Manager) — Clients never see it.
    queryset = Invoice.objects.select_related("booking", "booking__client").order_by("-id")
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated, IsStaffMember]
    pagination_class = None

    def get_queryset(self):
        queryset = super().get_queryset()
        status_param = self.request.query_params.get("status")
        search_param = self.request.query_params.get("search")
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")

        if status_param:
            queryset = queryset.filter(status=status_param)
        if search_param:
            queryset = queryset.filter(
                Q(invoice_number__icontains=search_param)
                | Q(booking__client__full_name__icontains=search_param)
                | Q(booking__service_name__icontains=search_param)
                | Q(payments__transaction_id__icontains=search_param)
            ).distinct()
        if date_from:
            queryset = queryset.filter(issued_date__date__gte=date_from)
        if date_to:
            # Issue 2 Fix: Expand date_to inclusive of the entire day (up to 23:59:59)
            queryset = queryset.filter(issued_date__date__lte=date_to)
        return queryset

    def list(self, request, *args, **kwargs):
        user_id = request.user.id
        status_param = request.query_params.get("status", "")
        search_param = request.query_params.get("search", "")
        date_from = request.query_params.get("date_from", "")
        date_to = request.query_params.get("date_to", "")

        cache_version = cache.get(f"invoice_version_{user_id}", 1)
        cache_key = f"invoice_list_v{cache_version}_{user_id}_{status_param}_{search_param}_{date_from}_{date_to}"

        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return Response(cached_data)

        response = super().list(request, *args, **kwargs)
        cache.set(cache_key, response.data, timeout=300)
        return response

    def perform_create(self, serializer):
        serializer.save()
        _bump_version(f"invoice_version_{self.request.user.id}")

    def perform_update(self, serializer):
        serializer.save()
        _bump_version(f"invoice_version_{self.request.user.id}")

    def perform_destroy(self, instance):
        instance.delete()
        _bump_version(f"invoice_version_{self.request.user.id}")
        _bump_version(f"payment_version_{self.request.user.id}")

    def get_permissions(self):
        # Refunds, and generic create/update/delete of invoices (which would
        # otherwise let any Staff member bypass the pay/unpaid/refund actions'
        # own checks), are Admin-only. A Booking Manager keeps list/retrieve/pay/unpaid.
        if self.action in ("refund", "create", "update", "partial_update", "destroy"):
            return [IsAuthenticated(), IsAdmin()]
        return super().get_permissions()

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        """Mark invoice as paid — applying discount/coupon validation."""
        invoice = self.get_object()
        payment_method = request.data.get("payment_method", "CASH")
        discount_amount = request.data.get("discount_amount")
        coupon_code = request.data.get("coupon_code", "")

        if (discount_amount not in (None, "") or coupon_code) and not is_admin(request.user):
            return Response(
                {"detail": "Only an Admin can apply discounts or coupons."}, status=403
            )

        try:
            BillingService.mark_invoice_paid(
                invoice, payment_method=payment_method,
                discount_amount=discount_amount, coupon_code=coupon_code,
                marked_by=request.user,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        _bump_version(f"invoice_version_{request.user.id}")
        _bump_version(f"payment_version_{request.user.id}")
        return Response(InvoiceSerializer(invoice).data)

    @action(detail=True, methods=["post"])
    def unpaid(self, request, pk=None):
        """Reverse a paid invoice back to unpaid."""
        invoice = self.get_object()

        try:
            BillingService.mark_invoice_unpaid(invoice)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        _bump_version(f"invoice_version_{request.user.id}")
        _bump_version(f"payment_version_{request.user.id}")
        return Response(InvoiceSerializer(invoice).data)

    @action(detail=True, methods=["post"])
    def refund(self, request, pk=None):
        invoice = self.get_object()
        reason = request.data.get("refund_reason", "")

        try:
            BillingService.refund_invoice(invoice, reason=reason, marked_by=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        _bump_version(f"invoice_version_{request.user.id}")
        _bump_version(f"payment_version_{request.user.id}")
        return Response(InvoiceSerializer(invoice).data)


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    # Payments is a Staff-only module (Admin or Booking Manager) — Clients never see it.
    queryset = Payment.objects.select_related("invoice", "invoice__booking", "invoice__booking__client").order_by("-id")
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated, IsStaffMember]
    pagination_class = None

    def get_permissions(self):
        # Revenue analytics are an Admin-only capability.
        if self.action == "summary":
            return [IsAuthenticated(), IsAdmin()]
        return super().get_permissions()

    def list(self, request, *args, **kwargs):
        user_id = request.user.id
        cache_version = cache.get(f"payment_version_{user_id}", 1)
        cache_key = f"payment_list_v{cache_version}_{user_id}"

        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return Response(cached_data)

        response = super().list(request, *args, **kwargs)
        cache.set(cache_key, response.data, timeout=300)
        return response

    @action(detail=False, methods=["get"])
    def summary(self, request):
        total_revenue = Payment.objects.filter(status="PAID").aggregate(sum=Sum("amount"))["sum"] or 0
        
        invoice_refunded = Invoice.objects.filter(status="REFUNDED").aggregate(sum=Sum("total_amount"))["sum"] or 0
        total_refunded = invoice_refunded if invoice_refunded > 0 else (Payment.objects.filter(status="REFUNDED").aggregate(sum=Sum("amount"))["sum"] or 0)

        unpaid_invoices = Invoice.objects.exclude(status__in=["PAID", "REFUNDED"])
        total_pending = sum(inv.total_amount for inv in unpaid_invoices)

        now = timezone.now()
        this_month_revenue = Payment.objects.filter(
            status="PAID"
        ).filter(
            Q(paid_at__year=now.year, paid_at__month=now.month) |
            Q(paid_at__isnull=True, invoice__issued_date__year=now.year, invoice__issued_date__month=now.month) |
            Q(paid_at__isnull=True, invoice__booking__booking_date__year=now.year, invoice__booking__booking_date__month=now.month)
        ).aggregate(sum=Sum("amount"))["sum"] or 0

        return Response({
            "total_revenue": total_revenue,
            "total_pending": total_pending,
            "total_refunded": total_refunded,
            "this_month_revenue": this_month_revenue,
        })