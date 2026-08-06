from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Sum, Q
from django.utils import timezone
from rest_framework.response import Response
from .models import Client
from .serializers import ClientSerializer, ClientDetailSerializer
from booking.models import Booking
from rest_framework.views import APIView
from django.core.cache import cache

class ClientViewSet(viewsets.ModelViewSet):
    """
    A ViewSet for viewing, creating, updating, and deleting clients.
    Provides searching, filtering, and sorting capabilities without pagination.
    """

    permission_classes = [IsAuthenticated]
    pagination_class = None  # Removes pagination to display all records on a single view
    queryset = Client.objects.all()
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["status"]
    search_fields = ["full_name", "email", "phone_number"]
    ordering_fields = ["full_name", "created_at", "status"]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ClientDetailSerializer
        return ClientSerializer

    def get_queryset(self): 
        user = self.request.user

        if self.action in ("update", "partial_update", "destroy"):
            queryset = Client.objects.all()
        else:
            client_ids = Booking.objects.filter(created_by=user).values_list(
                "client_id", flat=True
            )
            queryset = Client.objects.filter(Q(id__in=client_ids) | Q(bookings__isnull=True))

        if self.action == "retrieve" or self.action == "destroy":
                queryset = queryset.prefetch_related("bookings").annotate(
                total_bookings=Count("bookings"),
                total_completed_bookings=Count("bookings", filter=Q(bookings__status=Booking.BookingStatus.COMPLETED)),
                total_cancelled_bookings=Count("bookings", filter=Q(bookings__status=Booking.BookingStatus.CANCELLED)),
                total_amount_paid=Sum("bookings__price", filter=Q(bookings__payment_status=Booking.PaymentStatus.PAID), default=0.0),
            )
        return queryset

    def list(self, request, *args, **kwargs):
        user_id = request.user.id
        search_param = request.query_params.get("search", "")
        status_param = request.query_params.get("status", "")
        cache_key = f"client_list_{user_id}_{search_param}_{status_param}"

        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return Response(cached_data)
            
        response = super().list(request, *args, **kwargs)
        cache.set(cache_key, response.data, timeout=300)
        return response

    def _clear_client_cache(self, user_id):
        """Instantly invalidate cached client list search/filter variants."""
        if hasattr(cache, 'delete_pattern'):
            cache.delete_pattern(f"client_list_{user_id}_*")
        else:
            cache.clear()

    def perform_create(self, serializer):  
        serializer.save() 
        self._clear_client_cache(self.request.user.id)

    def perform_update(self, serializer):
        serializer.save()
        self._clear_client_cache(self.request.user.id)

    def perform_destroy(self, instance):
        user_id = self.request.user.id
        instance.delete()
        self._clear_client_cache(user_id)

    def retrieve(self, request, *args, **kwargs):
        self.instance = self.get_object()
        serializer = self.get_serializer(self.instance)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def me(self, request):
        """Return the Client record tied to the authenticated user's own account, creating it if needed."""
        client = Client.get_or_create_for_user(request.user)
        return Response(ClientSerializer(client).data)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.action == "retrieve" and hasattr(self, 'instance'):
            all_bookings = sorted(list(self.instance.bookings.all()), key=lambda b: (b.booking_date, b.start_time))
            
            today = timezone.now().date()
            upcoming = []
            history = []
            for booking in all_bookings:
                (upcoming if booking.booking_date >= today else history).append(booking)
            
            context['upcoming_bookings'] = upcoming
            context['booking_history'] = sorted(history, key=lambda b: (b.booking_date, b.start_time), reverse=True)
        return context

class DashboardSummaryView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        return Response({"message": "Dashboard summary"})