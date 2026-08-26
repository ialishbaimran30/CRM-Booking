from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from accounts.permissions import IsAdmin
from .services import ReportService
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from django.core.cache import cache

class DashboardSummaryAPIView(APIView):
    # Reports are an Admin-only module — Booking Managers have no access.
    permission_classes = [IsAuthenticated, IsAdmin]
    throttle_scope = "report"  # F-6: aggregates over every invoice — not free
    @method_decorator(vary_on_headers("Authorization"))
    def get(self, request):
        user_id = request.user.id
        booking_v = cache.get("booking_version_global", 1)
        payment_v = cache.get(f"payment_version_{user_id}", 1)
        client_v = cache.get(f"client_version_{user_id}", 1)
        
        cache_key = f"dashboard_summary_v{booking_v}_{payment_v}_{client_v}_{user_id}"
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return Response(cached_data, status=status.HTTP_200_OK)

        data = ReportService.get_dashboard_summary()
        cache.set(cache_key, data, timeout=300)
        return Response(data, status=status.HTTP_200_OK)


class PeriodicReportAPIView(APIView):
    # Reports are an Admin-only module — Booking Managers have no access.
    permission_classes = [IsAuthenticated, IsAdmin]
    throttle_scope = "report"  # F-6: aggregates over every invoice — not free
    @method_decorator(vary_on_headers("Authorization"))
    def get(self, request):
        user_id = request.user.id
        period = request.query_params.get("period", "monthly")
        
        booking_v = cache.get("booking_version_global", 1)
        payment_v = cache.get(f"payment_version_{user_id}", 1)
        client_v = cache.get(f"client_version_{user_id}", 1)
        
        cache_key = f"periodic_report_{period}_v{booking_v}_{payment_v}_{client_v}_{user_id}"
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return Response(cached_data, status=status.HTTP_200_OK)

        data = ReportService.get_periodic_report(period_type=period)
        cache.set(cache_key, data, timeout=300)
        return Response(data, status=status.HTTP_200_OK)