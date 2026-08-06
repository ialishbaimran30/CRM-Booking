from rest_framework import serializers
from .models import Booking, Waitlist
from clients.models import Client
from django.utils import timezone


class BookingSerializer(serializers.ModelSerializer):
    """Serializer for the Booking model."""

    client_full_name = serializers.CharField(source="client.full_name", read_only=True)
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
        read_only_fields = ("created_by", "created_at", "updated_at", "client_full_name")
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

    def validate(self, data):
        request = self.context.get("request")
        user = request.user if request else None

        # Enforce client restrictions on backend
        if user and not user.is_staff and not user.is_superuser:
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
        return data

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user:
            validated_data["created_by"] = request.user
            # Double-check safety guard on create
            if not request.user.is_staff and not request.user.is_superuser:
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

        if user and not user.is_staff and not user.is_superuser:
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