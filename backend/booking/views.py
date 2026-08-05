from rest_framework import viewsets, filters, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from datetime import time, timedelta, datetime
from django.db import transaction
from .models import Booking
from payments.models import Payment, Invoice
from .serializers import BookingSerializer
from django.core.cache import cache
from django.utils import timezone
import threading


class BookingViewSet(viewsets.ModelViewSet):
    queryset = Booking.objects.all()
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]
    # Disable pagination for bookings viewset
    pagination_class = None
    
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["status", "payment_status", "booking_date"]
    search_fields = ["client__full_name", "service_name", "booking_date"]
    ordering_fields = ["booking_date", "created_at", "client__full_name"]

    def get_queryset(self):
        if self.action in ("retrieve", "update", "partial_update", "destroy", "cancel", "reschedule"):
            return Booking.objects.all()
        return Booking.objects.filter(created_by=self.request.user)

    def _bump_cache_version(self, user_id):
        if user_id:
            v_booking = cache.get(f"booking_version_{user_id}", 1)
            cache.set(f"booking_version_{user_id}", v_booking + 1)
            v_payment = cache.get(f"payment_version_{user_id}", 1)
            cache.set(f"payment_version_{user_id}", v_payment + 1)

    def list(self, request, *args, **kwargs):
        user_id = request.user.id
        search_param = request.query_params.get("search", "")
        status_param = request.query_params.get("status", "")
        date_param = request.query_params.get("booking_date", "")
        
        cache_version = cache.get(f"booking_version_{user_id}", 1)
        cache_key = f"booking_list_v{cache_version}_{user_id}_{search_param}_{status_param}_{date_param}"
        
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return Response(cached_data)  
            
        response = super().list(request, *args, **kwargs)
        cache.set(cache_key, response.data, timeout=300)
        return response

    def perform_create(self, serializer):
        with transaction.atomic():
            booking = serializer.save(created_by=self.request.user)
            
            unique_inv_number = f"INV-{booking.id}-{timezone.now().strftime('%Y%m%d%H%M%S%f')}"
            is_paid = str(booking.payment_status).upper() == 'PAID'
            
            invoice, created = Invoice.objects.update_or_create(
                booking=booking,
                defaults={
                    'invoice_number': unique_inv_number,
                    'subtotal': booking.price or 0.00,
                    'total_amount': booking.price or 0.00,
                    'status': Invoice.PaymentStatus.PAID if is_paid else Invoice.PaymentStatus.UNPAID
                }
            )
            
            if is_paid:
                Payment.objects.update_or_create(
                    invoice=invoice,
                    defaults={
                        'amount': booking.price or 0.00,
                        'status': Payment.PaymentStatus.PAID
                    }
                )
            else:
                Payment.objects.filter(invoice=invoice).delete()

        def send_async_email():
            try:
                pass
            except Exception as email_err:
                print(f"Background email error: {email_err}")

        threading.Thread(target=send_async_email, daemon=True).start()
        self._bump_cache_version(self.request.user.id)

    def perform_update(self, serializer):
        with transaction.atomic():
            booking = serializer.save()
            
            if hasattr(booking, 'invoice'):
                invoice = booking.invoice
                invoice.subtotal = booking.price or invoice.subtotal
                invoice.total_amount = booking.price or invoice.total_amount
                
                status_val = str(booking.payment_status).upper()
                if status_val == 'PAID':
                    invoice.status = Invoice.PaymentStatus.PAID
                    Payment.objects.update_or_create(
                        invoice=invoice,
                        defaults={'amount': booking.price or 0.00, 'status': Payment.PaymentStatus.PAID}
                    )
                elif status_val == 'REFUNDED':
                    invoice.status = Invoice.PaymentStatus.REFUNDED
                    Payment.objects.filter(invoice=invoice).update(status=Payment.PaymentStatus.REFUNDED)
                else:
                    invoice.status = Invoice.PaymentStatus.UNPAID
                    Payment.objects.filter(invoice=invoice).delete()
                invoice.save()
        
        self._bump_cache_version(self.request.user.id)

    def update(self, request, *args, **kwargs):
        try:
            return super().update(request, *args, **kwargs)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def partial_update(self, request, *args, **kwargs):
        try:
            return super().partial_update(request, *args, **kwargs)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def perform_destroy(self, instance):
        user_id = instance.created_by.id if instance.created_by else None
        
        with transaction.atomic():
            # Clean up related payment/invoice records explicitly to prevent orphans
            if hasattr(instance, 'invoice') and instance.invoice:
                Payment.objects.filter(invoice=instance.invoice).delete()
                instance.invoice.delete()
            
            instance.delete()
            
        # Bump both caches so Payment and Booking modules update instantly
        self._bump_cache_version(user_id)