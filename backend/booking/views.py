from rest_framework import viewsets, filters, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from datetime import time, timedelta, datetime
from django.db import transaction, IntegrityError
from .models import Booking, Waitlist
from clients.models import Client
from payments.models import Payment, Invoice
from .serializers import BookingSerializer, WaitlistSerializer
from .slots import generate_daily_slots
from .emails import (
    notify_waitlist_for_freed_slot,
    send_booking_cancelled_email,
    send_booking_rescheduled_email,
    send_booking_updated_email,
)
from django.core.cache import cache
from django.utils import timezone
import threading

ACTIVE_STATUSES = (Booking.BookingStatus.PENDING, Booking.BookingStatus.CONFIRMED)


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
        user = self.request.user
        # Staff/admin accounts have full visibility over all bookings, including
        # ones created by clients through the Client Portal.
        if user.is_staff or user.is_superuser:
            return Booking.objects.all()

        # Strict Client Isolation: clients can only access bookings they created themselves.
        return Booking.objects.filter(created_by=user)

    @action(detail=False, methods=["get"], url_path="available-slots")
    def available_slots(self, request):
        """List the fixed business-hours slot grid for a date, marking each as
        available or booked, so clients/staff always see live availability."""
        date_param = request.query_params.get("date")
        if not date_param:
            return Response({"detail": "A 'date' query parameter is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            target_date = datetime.strptime(date_param, "%Y-%m-%d").date()
        except ValueError:
            return Response({"detail": "Invalid date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        is_staff = user.is_staff or user.is_superuser
        my_client = None if is_staff else Client.get_or_create_for_user(user)

        existing = list(
            Booking.objects.filter(booking_date=target_date, status__in=ACTIVE_STATUSES).select_related("client")
        )
        waitlisted_slots = set(
            Waitlist.objects.filter(booking_date=target_date).values_list("start_time", "end_time")
        )
        my_waitlisted_slots = set()
        if my_client is not None:
            my_waitlisted_slots = set(
                Waitlist.objects.filter(booking_date=target_date, client=my_client).values_list("start_time", "end_time")
            )

        slots = []
        for slot_start, slot_end in generate_daily_slots():
            conflict = next(
                (b for b in existing if b.start_time < slot_end and b.end_time > slot_start), None
            )
            entry = {
                "start_time": slot_start.strftime("%H:%M:%S"),
                "end_time": slot_end.strftime("%H:%M:%S"),
                "available": conflict is None,
            }
            if conflict is not None:
                entry["booking_id"] = conflict.id
                if is_staff:
                    entry["client_name"] = conflict.client.full_name
                    entry["waitlist_count"] = sum(
                        1 for s, e in waitlisted_slots if s == slot_start and e == slot_end
                    )
                if my_client is not None:
                    entry["on_waitlist"] = (slot_start, slot_end) in my_waitlisted_slots
            slots.append(entry)

        return Response({"date": date_param, "slots": slots})

    def _bump_cache_version(self, user_id=None):
        # The booking list version is global (not per-user): a booking created
        # by one user (e.g. a client) must invalidate every other user's
        # cached list (e.g. staff viewing the Admin CRM) so it shows up
        # immediately, instead of only invalidating the acting user's cache.
        v_booking = cache.get("booking_version_global", 1)
        cache.set("booking_version_global", v_booking + 1)

        # Payment cache invalidation stays per-user, matching the scheme used
        # by the payments/reports apps elsewhere.
        if user_id:
            v_payment = cache.get(f"payment_version_{user_id}", 1)
            cache.set(f"payment_version_{user_id}", v_payment + 1)

    def list(self, request, *args, **kwargs):
        user_id = request.user.id
        search_param = request.query_params.get("search", "")
        status_param = request.query_params.get("status", "")
        date_param = request.query_params.get("booking_date", "")

        cache_version = cache.get("booking_version_global", 1)
        cache_key = f"booking_list_v{cache_version}_{user_id}_{search_param}_{status_param}_{date_param}"
        
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return Response(cached_data)  
            
        response = super().list(request, *args, **kwargs)
        cache.set(cache_key, response.data, timeout=300)
        return response

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except IntegrityError:
            # DB-level backstop: two requests raced past the serializer's
            # overlap check for the same slot: the unique constraint on
            # (booking_date, start_time) for active bookings caught it.
            return Response(
                {"non_field_errors": ["This slot has already been booked by another client. Please choose another slot."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
        old_instance = serializer.instance
        old_date = old_instance.booking_date
        old_start = old_instance.start_time
        old_end = old_instance.end_time
        old_status = old_instance.status
        old_service_name = old_instance.service_name
        old_price = old_instance.price
        old_payment_status = old_instance.payment_status

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

        # The old slot frees up if the booking was just cancelled, or if it
        # was rescheduled to a different date/time (still active elsewhere).
        slot_changed = (old_date, old_start, old_end) != (booking.booking_date, booking.start_time, booking.end_time)
        just_cancelled = old_status in ACTIVE_STATUSES and booking.status == Booking.BookingStatus.CANCELLED
        rescheduled = booking.status in ACTIVE_STATUSES and slot_changed
        if just_cancelled or rescheduled:
            booking._waitlist_notified_count = notify_waitlist_for_freed_slot(old_date, old_start, old_end)

        # Notify the booking's own client — exactly one email per update,
        # matching whichever change is most significant to them.
        if just_cancelled:
            booking._client_notification_sent = send_booking_cancelled_email(booking)
        elif rescheduled:
            booking._client_notification_sent = send_booking_rescheduled_email(booking, old_date, old_start, old_end)
        else:
            other_change = (
                old_service_name != booking.service_name
                or old_price != booking.price
                or old_payment_status != booking.payment_status
                or old_status != booking.status
            )
            if other_change:
                booking._client_notification_sent = send_booking_updated_email(booking)

    def update(self, request, *args, **kwargs):
        try:
            return super().update(request, *args, **kwargs)
        except IntegrityError:
            return Response(
                {"non_field_errors": ["This slot has already been booked by another client. Please choose another slot."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def partial_update(self, request, *args, **kwargs):
        try:
            return super().partial_update(request, *args, **kwargs)
        except IntegrityError:
            return Response(
                {"non_field_errors": ["This slot has already been booked by another client. Please choose another slot."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def perform_destroy(self, instance):
        user_id = instance.created_by.id if instance.created_by else None
        old_date, old_start, old_end, old_status = (
            instance.booking_date, instance.start_time, instance.end_time, instance.status
        )

        # Notify the booking's own client before the row is gone — the
        # instance (and its client FK) won't exist to read after .delete().
        if old_status in ACTIVE_STATUSES:
            send_booking_cancelled_email(instance, deleted=True)

        with transaction.atomic():
            # Clean up related payment/invoice records explicitly to prevent orphans
            if hasattr(instance, 'invoice') and instance.invoice:
                Payment.objects.filter(invoice=instance.invoice).delete()
                instance.invoice.delete()

            instance.delete()

        # Bump both caches so Payment and Booking modules update instantly
        self._bump_cache_version(user_id)

        # Deleting an active booking frees its slot up just like a cancel does.
        if old_status in ACTIVE_STATUSES:
            notify_waitlist_for_freed_slot(old_date, old_start, old_end)


class WaitlistViewSet(viewsets.ModelViewSet):
    """Clients asking to be notified when a booked slot frees up."""

    queryset = Waitlist.objects.all()
    serializer_class = WaitlistSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return Waitlist.objects.all()
        return Waitlist.objects.filter(client__email__iexact=user.email)

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except IntegrityError:
            return Response(
                {"non_field_errors": ["You are already on the waitlist for this slot."]},
                status=status.HTTP_400_BAD_REQUEST,
            )