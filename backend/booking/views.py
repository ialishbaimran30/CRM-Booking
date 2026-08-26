from rest_framework import viewsets, filters, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from datetime import time, timedelta, datetime
from django.db import transaction, IntegrityError
from accounts.permissions import IsAdminOrReadOnly, IsStaffMember, is_staff_member
from core.alerting import alert_on_booking_cancellation_spike
from core.audit import record_audit_event
from core.models import AuditLog
from notifications.services import CommunicationService
from .models import Booking, Service, Waitlist
from clients.models import Client
from payments.models import Payment, Invoice
from .serializers import BookingSerializer, ServiceSerializer, WaitlistSerializer
from .slots import generate_daily_slots
from .emails import (
    notify_waitlist_for_freed_slot,
    send_booking_cancelled_email,
    send_booking_rescheduled_email,
    send_booking_updated_email,
)
from .google_calendar import GoogleCalendarService
from django.core.cache import cache
from django.utils import timezone
import logging
import threading

logger = logging.getLogger(__name__)


def _notify_waitlist_slot_available_in_app(booking_date, start_time, end_time):
    """In-app companion to notify_waitlist_for_freed_slot (booking/emails.py,
    unchanged) — additive only, never allowed to raise."""
    try:
        entries = Waitlist.objects.filter(
            booking_date=booking_date, start_time=start_time, end_time=end_time
        ).select_related("client")
        for entry in entries:
            CommunicationService.notify_waitlist_slot_available(entry)
    except Exception:
        logger.exception("Failed to send in-app waitlist-availability notifications")

ACTIVE_STATUSES = (Booking.BookingStatus.PENDING, Booking.BookingStatus.CONFIRMED)


class ServiceViewSet(viewsets.ModelViewSet):
    """The Admin-defined catalog of bookable services and their hourly rates.
    Any authenticated user (Staff or Client) may browse it to book; only the
    Admin may define/edit rates."""

    queryset = Service.objects.all().order_by("name")
    serializer_class = ServiceSerializer
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]
    pagination_class = None


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

    def get_permissions(self):
        # Deleting a booking cascades into its Invoice/Payment records, which
        # are Staff-only elsewhere in the app — Clients must cancel instead
        # (PATCH status=CANCELLED), never hard-delete.
        if self.action == "destroy":
            return [IsAuthenticated(), IsStaffMember()]
        return super().get_permissions()

    def get_queryset(self):
        user = self.request.user
        # Staff (Admin or Booking Manager) have full visibility over all bookings,
        # including ones created by clients through the Client Portal.
        if is_staff_member(user):
            return Booking.objects.all()

        # Strict Client Isolation: a booking belongs to a client by its
        # `client` association, not by who created it — Admin/Booking
        # Manager routinely create bookings on a client's behalf, and those
        # must still show up in that client's own My Bookings. Matching by
        # `created_by` here would only ever surface bookings the client
        # created themselves. Matches the same email-based lookup already
        # used for Waitlist (WaitlistViewSet.get_queryset, below) and for
        # resolving "my own client record" (Client.get_or_create_for_user).
        return Booking.objects.filter(client__email__iexact=user.email)

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
        is_staff = is_staff_member(user)
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

        try:
            CommunicationService.notify_booking_event(booking, actor=self.request.user, action="created")
        except Exception:
            logger.exception("Failed to send in-app booking-created notifications for booking %s", booking.id)

        self._sync_calendar_on_create(booking)

    def _sync_calendar_on_create(self, booking):
        """Best-effort Calendar sync — a failure here must never fail the
        booking, which has already been committed above."""
        try:
            ok, event_id, error = GoogleCalendarService.create_event(booking)
            if ok:
                booking.google_event_id = event_id
                booking.calendar_sync_status = Booking.CalendarSyncStatus.SYNCED
                booking.calendar_sync_error = ""
            else:
                booking.calendar_sync_status = Booking.CalendarSyncStatus.FAILED
                booking.calendar_sync_error = error or ""
                logger.error("Google Calendar sync failed for booking %s: %s", booking.id, error)
            booking.save(update_fields=["google_event_id", "calendar_sync_status", "calendar_sync_error"])
        except Exception:
            logger.exception("Unexpected error syncing booking %s to Google Calendar", booking.id)

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
        if just_cancelled:
            record_audit_event(
                actor=self.request.user, action=AuditLog.Action.BOOKING_CANCELLED, target=booking,
                changes={"before_status": old_status, "after_status": booking.status}, request=self.request,
            )
            alert_on_booking_cancellation_spike()
        if just_cancelled or rescheduled:
            booking._waitlist_notified_count = notify_waitlist_for_freed_slot(old_date, old_start, old_end)
            _notify_waitlist_slot_available_in_app(old_date, old_start, old_end)

        other_change = (
            old_service_name != booking.service_name
            or old_price != booking.price
            or old_payment_status != booking.payment_status
            or old_status != booking.status
        )

        # Notify the booking's own client — exactly one email per update,
        # matching whichever change is most significant to them. The in-app
        # + WebSocket notification (Admin/Booking Manager/Client, per
        # notify_booking_event's recipient rule) mirrors the exact same
        # classification, so one update still produces one logical event.
        try:
            if just_cancelled:
                booking._client_notification_sent = send_booking_cancelled_email(booking)
                CommunicationService.notify_booking_event(
                    booking, actor=self.request.user, action="cancelled",
                    previous_value=f"{old_date.strftime('%d %b')}, {old_start.strftime('%I:%M %p')}",
                )
            elif rescheduled:
                booking._client_notification_sent = send_booking_rescheduled_email(booking, old_date, old_start, old_end)
                CommunicationService.notify_booking_event(
                    booking, actor=self.request.user, action="rescheduled",
                    previous_value=f"{old_date.strftime('%d %b')}, {old_start.strftime('%I:%M %p')}",
                    new_value=f"{booking.booking_date.strftime('%d %b')}, {booking.start_time.strftime('%I:%M %p')}",
                )
            elif other_change:
                booking._client_notification_sent = send_booking_updated_email(booking)
                CommunicationService.notify_booking_event(booking, actor=self.request.user, action="updated")
        except Exception:
            logger.exception("Failed to send in-app booking-update notifications for booking %s", booking.id)

        self._sync_calendar_on_update(booking, just_cancelled=just_cancelled, changed=rescheduled or other_change)

    def _sync_calendar_on_update(self, booking, *, just_cancelled, changed):
        """Best-effort Calendar sync mirroring the cancel/reschedule/update
        classification already computed above — never fails the update."""
        try:
            if just_cancelled:
                ok, _event_id, error = GoogleCalendarService.delete_event(booking)
                if ok:
                    booking.google_event_id = None
                    booking.calendar_sync_status = Booking.CalendarSyncStatus.CANCELLED
                    booking.calendar_sync_error = ""
                else:
                    booking.calendar_sync_status = Booking.CalendarSyncStatus.FAILED
                    booking.calendar_sync_error = error or ""
                    logger.error("Google Calendar delete failed for booking %s: %s", booking.id, error)
                booking.save(update_fields=["google_event_id", "calendar_sync_status", "calendar_sync_error"])
            elif changed:
                ok, event_id, error = GoogleCalendarService.update_event(booking)
                if ok:
                    booking.google_event_id = event_id
                    booking.calendar_sync_status = Booking.CalendarSyncStatus.SYNCED
                    booking.calendar_sync_error = ""
                else:
                    booking.calendar_sync_status = Booking.CalendarSyncStatus.FAILED
                    booking.calendar_sync_error = error or ""
                    logger.error("Google Calendar sync failed for booking %s: %s", booking.id, error)
                booking.save(update_fields=["google_event_id", "calendar_sync_status", "calendar_sync_error"])
        except Exception:
            logger.exception("Unexpected error syncing booking %s to Google Calendar", booking.id)

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
        record_audit_event(
            actor=self.request.user, action=AuditLog.Action.BOOKING_DELETED, target=instance,
            changes={
                "status": old_status,
                "booking_date": str(old_date),
                "client_email": instance.client.email if instance.client else None,
            },
            request=self.request,
        )

        # Notify the booking's own client before the row is gone — the
        # instance (and its client FK) won't exist to read after .delete().
        if old_status in ACTIVE_STATUSES:
            send_booking_cancelled_email(instance, deleted=True)
            try:
                CommunicationService.notify_booking_event(
                    instance, actor=self.request.user, action="cancelled",
                    previous_value=f"{old_date.strftime('%d %b')}, {old_start.strftime('%I:%M %p')}",
                )
            except Exception:
                logger.exception("Failed to send in-app booking-deleted notifications for booking %s", instance.id)

        # Hard delete: remove the Calendar event first, before the CRM row
        # (which holds google_event_id) is gone.
        if instance.google_event_id:
            try:
                GoogleCalendarService.delete_event(instance)
            except Exception:
                logger.exception("Failed to delete Google Calendar event for booking %s", instance.id)

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
            _notify_waitlist_slot_available_in_app(old_date, old_start, old_end)


class WaitlistViewSet(viewsets.ModelViewSet):
    """Clients asking to be notified when a booked slot frees up."""

    queryset = Waitlist.objects.all()
    serializer_class = WaitlistSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        if is_staff_member(user):
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