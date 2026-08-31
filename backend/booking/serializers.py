from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from rest_framework import serializers
from accounts.permissions import is_staff_member
from .models import Booking, Service, Waitlist
from clients.models import Client
from django.utils import timezone


def _duration_hours(start_time, end_time):
    """Exact decimal hours between two `time` values (end assumed after start)."""
    delta = datetime.combine(date.min, end_time) - datetime.combine(date.min, start_time)
    return Decimal(delta.seconds) / Decimal(3600)


def _calculate_total(duration_hours, hourly_rate):
    return (duration_hours * hourly_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ["id", "name", "hourly_rate", "description", "is_active"]


class BookingSerializer(serializers.ModelSerializer):
    """Serializer for the Booking model."""

    client_full_name = serializers.CharField(source="client.full_name", read_only=True)
    # Only active services may be newly selected; a booking already linked to
    # a since-deactivated service still displays/reads fine (write-only restriction).
    service = serializers.PrimaryKeyRelatedField(queryset=Service.objects.filter(is_active=True), required=False, allow_null=True)
    # Backend-derived from the selected service when one is provided (see
    # _apply_backend_pricing) — only required as free text on the legacy
    # no-Service manual path.
    service_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    # Backend-calculated when a service is selected; only Staff may submit
    # this directly, and only on the legacy no-Service manual path.
    price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    # Read-only, informational — backend-computed from start/end time.
    duration_hours = serializers.SerializerMethodField()
    # Set by the post_save signal in booking/signals.py; None until a create actually runs it.
    email_sent = serializers.SerializerMethodField()
    # Set in BookingViewSet.perform_update when a cancel/reschedule frees a
    # slot that had clients waiting on it; None otherwise.
    waitlist_notified_count = serializers.SerializerMethodField()
    # Set in BookingViewSet.perform_update whenever the booking's own client
    # was emailed about the change (cancel/reschedule/other update); None if
    # nothing changed that warranted a notification.
    client_notification_sent = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = "__all__"
        # `rate_snapshot` is always backend-set (see _apply_backend_pricing).
        # `price` stays writable at the field level (Staff need it for the
        # legacy no-Service manual-price path) but `_apply_backend_pricing`
        # is the sole authority that decides whose submitted value survives —
        # it always overwrites `price` when a Service is involved, and strips
        # it entirely for non-Staff on the no-Service fallback. Never trust
        # `data['price']` as-received. `payment_status` may only ever change
        # via the Invoice pay/unpaid/refund actions in the payments app,
        # never through this generic booking endpoint.
        read_only_fields = (
            "created_by", "created_at", "updated_at", "client_full_name",
            "rate_snapshot", "payment_status",
            "google_event_id", "calendar_sync_status", "calendar_sync_error",
        )
        # Disable DRF's auto-generated UniqueTogetherValidator (from the
        # conditional UniqueConstraint on Meta.constraints) — it fires before
        # our own validate() below and produces a generic "must make a unique
        # set" message instead of distinguishing "your own booking" from
        # "another client's booking". The DB constraint still backstops races
        # via the IntegrityError catch in BookingViewSet.
        validators = []

    def get_email_sent(self, obj):
        return getattr(obj, "_email_sent", None)

    def get_waitlist_notified_count(self, obj):
        return getattr(obj, "_waitlist_notified_count", None)

    def get_client_notification_sent(self, obj):
        return getattr(obj, "_client_notification_sent", None)

    def get_duration_hours(self, obj):
        if not (obj.start_time and obj.end_time):
            return None
        return float(_duration_hours(obj.start_time, obj.end_time))

    def validate_status(self, value):
        request = self.context.get("request")
        user = request.user if request else None
        if user and not is_staff_member(user):
            if not self.instance:
                # Clients never choose the initial status; the model default (PENDING) applies.
                raise serializers.ValidationError("You cannot set a booking's status.")
            current = self.instance.status
            # The edit form always echoes the booking's current status back,
            # so a client changing only the time/notes re-submits it unchanged
            # — that must not count as a status change. The only status change
            # a client may make is a cancellation.
            if value != current and value != Booking.BookingStatus.CANCELLED:
                raise serializers.ValidationError("You can only cancel your own booking.")
            if value == Booking.BookingStatus.CANCELLED and current == Booking.BookingStatus.CANCELLED:
                raise serializers.ValidationError("This booking is already cancelled.")
        return value

    def validate(self, data):
        request = self.context.get("request")
        user = request.user if request else None

        # Enforce client restrictions on backend
        if user and not is_staff_member(user):
            own_client = Client.get_or_create_for_user(user)

            # If a client attempts to pass a different client ID, override or throw error
            if 'client' in data and data['client'] != own_client:
                raise serializers.ValidationError({"client": "You can only create bookings for your own account."})

            data['client'] = own_client

        start_time = data.get('start_time')
        end_time = data.get('end_time')
        booking_date = data.get('booking_date') or (self.instance.booking_date if self.instance else None)
        client = data.get('client') or (self.instance.client if self.instance else None)

        if start_time and end_time and start_time >= end_time:
            raise serializers.ValidationError({"end_time": "End time must be after start time."})

        if booking_date and start_time and end_time:
            # Slots are a shared, globally exclusive resource (one booking per
            # date+time regardless of which client holds it) — this is what
            # makes the Available Slots / waitlist feature meaningful.
            queryset = Booking.objects.filter(
                booking_date=booking_date,
                status__in=[Booking.BookingStatus.CONFIRMED, Booking.BookingStatus.PENDING]
            )
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)
            conflict = queryset.filter(
                start_time__lt=end_time, end_time__gt=start_time
            ).select_related("client").first()
            if conflict:
                if client and conflict.client_id == getattr(client, "id", None):
                    raise serializers.ValidationError({"non_field_errors": ["You already have a booking at this time."]})
                raise serializers.ValidationError({"non_field_errors": ["This slot has already been booked by another client."]})

        self._apply_backend_pricing(data, user)
        return data

    def _apply_backend_pricing(self, data, user):
        """Backend-controlled pricing: never trust a client-supplied price.
        A Service drives the calculation (duration * hourly rate, snapshotted);
        only Staff may fall back to the legacy manual-price path when no
        Service is selected at all (e.g. an ad-hoc booking)."""
        is_staff = bool(user and is_staff_member(user))
        service_provided = 'service' in data
        service = data.get('service') if service_provided else (self.instance.service if self.instance else None)

        if service is None:
            if not is_staff:
                if not self.instance:
                    raise serializers.ValidationError({"service": "Select a service to book."})
                # A Client editing their own legacy (pre-Service) booking —
                # never trust a client-supplied price; leave the stored value untouched.
                data.pop('price', None)
                return
            # Legacy/manual path (Staff only, no catalog Service): trust
            # whatever price they submitted (create), or leave it untouched (update).
            if not self.instance and 'price' not in data:
                raise serializers.ValidationError({"price": "Select a service, or enter a price manually."})
            return

        start_time = data.get('start_time', self.instance.start_time if self.instance else None)
        end_time = data.get('end_time', self.instance.end_time if self.instance else None)
        if not (start_time and end_time):
            return

        duration_hours = _duration_hours(start_time, end_time)

        if service_provided:
            # A (new) service was explicitly selected — take a fresh rate snapshot.
            rate = service.hourly_rate
        else:
            # Times changed but the service didn't — keep the original locked-in rate
            # so a later Service.hourly_rate edit never retroactively changes this booking.
            rate = self.instance.rate_snapshot if self.instance and self.instance.rate_snapshot is not None else service.hourly_rate

        data['rate_snapshot'] = rate
        data['price'] = _calculate_total(duration_hours, rate)
        data['service_name'] = service.name

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user:
            validated_data["created_by"] = request.user
            # Double-check safety guard on create
            if not is_staff_member(request.user):
                validated_data["client"] = Client.get_or_create_for_user(request.user)

        booking = super().create(validated_data)

        # If the booking client had asked to be notified for this exact slot,
        # they've now claimed it — drop their waitlist entry for it.
        Waitlist.objects.filter(
            client=booking.client,
            booking_date=booking.booking_date,
            start_time=booking.start_time,
            end_time=booking.end_time,
        ).delete()

        return booking

    def update(self, instance, validated_data):
        booking = super().update(instance, validated_data)

        # Same cleanup as create(): the booking now occupies this exact slot,
        # so if its client was on the waitlist for it (e.g. they rescheduled
        # into a slot that just freed up), that request is now fulfilled —
        # drop the stale entry. Runs inside BookingViewSet.perform_update's
        # transaction.atomic() block, so the booking move and the waitlist
        # removal commit together or not at all.
        Waitlist.objects.filter(
            client=booking.client,
            booking_date=booking.booking_date,
            start_time=booking.start_time,
            end_time=booking.end_time,
        ).delete()

        return booking

    def validate_booking_date(self, value):
        if value < timezone.now().date():
            raise serializers.ValidationError("Booking date cannot be in the past.")
        return value


class WaitlistSerializer(serializers.ModelSerializer):
    """Serializer for a client's request to be notified when a slot frees up."""

    client_full_name = serializers.CharField(source="client.full_name", read_only=True)
    client_email = serializers.CharField(source="client.email", read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = Waitlist
        fields = (
            "id", "client", "client_full_name", "client_email",
            "booking_date", "start_time", "end_time", "created_at", "notified_at", "status",
        )
        read_only_fields = ("created_at", "notified_at")
        extra_kwargs = {"client": {"required": False}}
        # Disable DRF's auto-generated UniqueTogetherValidator (from the
        # model's UniqueConstraint) — it force-overrides `required` back to
        # True for every field in the constraint, breaking the "client
        # defaults to yourself" flow above. Uniqueness is still enforced at
        # the DB level and surfaced via the IntegrityError catch in
        # WaitlistViewSet.create().
        validators = []

    def get_status(self, obj):
        return "NOTIFIED" if obj.notified_at else "WAITING"

    def validate(self, data):
        request = self.context.get("request")
        user = request.user if request else None

        if user and not is_staff_member(user):
            # Clients can only ever join the waitlist for themselves.
            data["client"] = Client.get_or_create_for_user(user)
        elif "client" not in data:
            raise serializers.ValidationError({"client": "This field is required."})

        start_time = data.get("start_time")
        end_time = data.get("end_time")
        if start_time and end_time and start_time >= end_time:
            raise serializers.ValidationError({"end_time": "End time must be after start time."})
        return data

    def validate_booking_date(self, value):
        if value < timezone.now().date():
            raise serializers.ValidationError("Booking date cannot be in the past.")
        return value