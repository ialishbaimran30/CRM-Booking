from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Notification
from .serializers import NotificationSerializer


class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Users can only view their own notifications (Notification Bell feature)
        return Notification.objects.filter(recipient=self.request.user).order_by("-created_at")

    # M-4: no cache_page here — it keyed on Vary: Authorization, which is
    # absent for session-authenticated requests (SessionAuthentication is
    # enabled globally), collapsing every such caller onto one shared cache
    # entry and leaking one user's notifications to another. The query
    # itself is a single indexed lookup, so caching bought little anyway.

    def perform_create(self, serializer):
        serializer.save(recipient=self.request.user)

    @action(detail=True, methods=["post"])
    def mark_as_read(self, request, pk=None):
        """Marks a specific notification as read."""
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        return Response({"status": "notification marked as read"}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="mark_all_as_read")
    def mark_all_as_read(self, request):
        """Marks every one of the current user's own notifications as read."""
        self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({"status": "all notifications marked as read"}, status=status.HTTP_200_OK)