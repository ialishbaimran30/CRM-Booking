from rest_framework import serializers
from django.db.models import Sum, Q
from django.utils import timezone
from rest_framework.validators import UniqueValidator
import re
from .models import Client
from booking.models import Booking
from booking.serializers import BookingSerializer
import re


def validate_phone_number(value):
    """
    Validates that the phone number is in a valid format.
    """
    if value and not re.match(r"^\+?\d{9,15}$", value):
        raise serializers.ValidationError("Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed.")


class ClientSerializer(serializers.ModelSerializer):
    """Serializer for the Client model."""

    phone_number = serializers.CharField(validators=[validate_phone_number], allow_blank=True, required=False)
    email = serializers.EmailField(
        max_length=255,
        validators=[UniqueValidator(queryset=Client.objects.all(), message="A client with this email already exists.")]
    )
    class Meta:
        model = Client
        fields = [
            "id",
            "full_name",
            "email", 
            "phone_number",
            "address",
            "city",
            "country",
            "notes",
            "status",
            "created_at",
            "updated_at",
        ]
        validators = []
        
    def validate_email(self, value):
        if not value:
            return value
        
        # Lowercase the email for proper checking
        email = value.lower().strip()

        # Check basic structure (must contain @ and a valid domain extension)
        email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(email_regex, email):
            raise serializers.ValidationError("Please enter a valid email address (e.g., example@gmail.com).")

        # Check for common typos
        invalid_domains = ['gamil.com', 'gmal.com', 'gmai.com', 'gamil.co', 'gmal.co', 'yaho.com', 'hotmai.com']
        domain = email.split('@')[-1]
        
        if domain in invalid_domains:
            raise serializers.ValidationError("Please enter a valid email address with correct spelling (e.g., @gmail.com).")
            
        return value


class ClientDetailSerializer(ClientSerializer):
    """Serializer for the Client model with detailed booking information."""

    total_bookings = serializers.IntegerField(read_only=True)
    total_completed_bookings = serializers.IntegerField(read_only=True)
    total_cancelled_bookings = serializers.IntegerField(read_only=True)
    total_amount_paid = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    upcoming_bookings = serializers.SerializerMethodField()
    booking_history = serializers.SerializerMethodField()

    class Meta(ClientSerializer.Meta):
        fields = ClientSerializer.Meta.fields + [
            "total_bookings",
            "total_completed_bookings",
            "total_cancelled_bookings",
            "total_amount_paid",
            "upcoming_bookings",
            "booking_history",
        ]

    def get_upcoming_bookings(self, obj):
        bookings = self.context.get('upcoming_bookings', [])
        return BookingSerializer(bookings, many=True, context=self.context).data

    def get_booking_history(self, obj):
        bookings = self.context.get('booking_history', [])
        return BookingSerializer(bookings, many=True, context=self.context).data