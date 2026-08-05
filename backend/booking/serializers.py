from rest_framework import serializers
from .models import Booking
from django.utils import timezone


class BookingSerializer(serializers.ModelSerializer):
    """Serializer for the Booking model."""

    client_full_name = serializers.CharField(source="client.full_name", read_only=True)

    class Meta:
        model = Booking
        fields = "__all__"
        # fields = [
        #     "id",
        #     "client",
        #     "client_full_name",
        #     "service_name",
        #     "booking_date",
        #     "start_time",
        #     "end_time",
        #     "status",
        #     "notes",
        #     "price",
        #     "payment_status",
        #     "created_at",
        #     "updated_at",
        # ]
        read_only_fields = ("created_by","created_at", "updated_at", "client_full_name")

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)

    def validate_booking_date(self, value):
        """
        Check that the booking date is not in the past.
        """
        if value < timezone.now().date():
            raise serializers.ValidationError("Booking date cannot be in the past.")
        return value

    def validate(self, data):
        """
        Check that start is before end.
        Check for overlapping bookings for the same client.
        """
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        booking_date = data.get('booking_date') or (self.instance.booking_date if self.instance else None)
        client = data.get('client') or (self.instance.client if self.instance else None)

        if start_time and end_time and start_time >= end_time:
            raise serializers.ValidationError({"end_time": "End time must be after start time."})

        if booking_date and start_time and end_time and client:
            # Exclude current instance when updating
            queryset = Booking.objects.filter(
                client=client,
                booking_date=booking_date,
                status__in=[Booking.BookingStatus.CONFIRMED, Booking.BookingStatus.PENDING]
            )
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)

            # Check for duplicate booking
            if queryset.filter(start_time=start_time, end_time=end_time).exists():
                raise serializers.ValidationError("A booking with this exact time already exists for this client.")

            # Check for overlapping bookings
            if queryset.filter(start_time__lt=end_time, end_time__gt=start_time).exists():
                raise serializers.ValidationError("This booking overlaps with an existing booking for this client.")

        return data
