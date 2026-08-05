from rest_framework.exceptions import ValidationError
from .models import BookingAssignment


class ResourceSchedulingService:
    """Service layer to manage and validate staff/resource conflict check."""

    @staticmethod
    def validate_assignment_conflicts(booking, staff, resource, start_time, end_time, booking_date):
        """Checks if the requested staff or resource is already booked during the given time slot."""
        
        conflicting_assignments = BookingAssignment.objects.filter(
            booking__booking_date=booking_date,
            booking__status__in=["PENDING", "CONFIRMED"]
        ).exclude(booking=booking)

        if staff:
            staff_conflict = conflicting_assignments.filter(
                staff=staff,
                booking__start_time__lt=end_time,
                booking__end_time__gt=start_time
            ).exists()
            if staff_conflict:
                raise ValidationError({"staff": "This staff member is already booked during this time slot."})

        if resource:
            resource_conflict = conflicting_assignments.filter(
                resource=resource,
                booking__start_time__lt=end_time,
                booking__end_time__gt=start_time
            ).exists()
            if resource_conflict:
                raise ValidationError({"resource": "This resource/room is already booked during this time slot."})

    @staticmethod
    def assign_to_booking(booking, staff=None, resource=None):
        """Creates or updates assignment mapping safely."""
        ResourceSchedulingService.validate_assignment_conflicts(
            booking=booking,
            staff=staff,
            resource=resource,
            start_time=booking.start_time,
            end_time=booking.end_time,
            booking_date=booking.booking_date
        )

        assignment, _ = BookingAssignment.objects.update_or_create(
            booking=booking,
            defaults={"staff": staff, "resource": resource}
        )
        return assignment