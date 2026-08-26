from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Sum, Q
from accounts.permissions import IsAdmin
from clients.models import Client
from booking.models import Booking
from django.utils import timezone
from payments.models import Payment

class DashboardSummaryView(APIView):
    """
    Provides a summary of key metrics for the logged-in user's dashboard.
    """
    # The Dashboard module is Admin-only — Booking Managers land on Clients instead.
    permission_classes = [IsAuthenticated, IsAdmin]
    throttle_scope = "report"  # F-6

    # M-4: no cache_page here — see notifications/views.py for why
    # (Vary: Authorization is absent for session-authenticated requests,
    # collapsing every such caller onto one shared, per-user-data cache entry).
    def get(self, request, *args, **kwargs):
        user = request.user

        # Filter bookings and clients relevant to the user
        user_bookings = Booking.objects.filter(created_by=user)
        client_ids = user_bookings.values_list("client_id", flat=True).distinct()
        user_clients = Client.objects.filter(id__in=client_ids)

        # Aggregations
        total_bookings = user_bookings.count()
        pending_bookings = user_bookings.filter(status=Booking.BookingStatus.PENDING).count()
        confirmed_bookings = user_bookings.filter(status=Booking.BookingStatus.CONFIRMED).count()
        completed_bookings = user_bookings.filter(status=Booking.BookingStatus.COMPLETED).count()
        cancelled_bookings = user_bookings.filter(status=Booking.BookingStatus.CANCELLED).count()
        
        revenue_collected = user_bookings.filter(
           status="PAID",
            invoice__booking__created_by=user
        ).aggregate(total=Sum('price'))['total'] or 0.00

        summary_data = {
            "total_clients": user_clients.count(),
            "total_bookings": total_bookings,
            "pending_bookings": pending_bookings,
            "confirmed_bookings": confirmed_bookings,
            "completed_bookings": completed_bookings,
            "cancelled_bookings": cancelled_bookings,
            "revenue_collected": revenue_collected,
        }

        return Response(summary_data)
