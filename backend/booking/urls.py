from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import BookingViewSet, ServiceViewSet, WaitlistViewSet

router = DefaultRouter()
router.register(r"bookings", BookingViewSet, basename="booking")
router.register(r"waitlist", WaitlistViewSet, basename="waitlist")
router.register(r"services", ServiceViewSet, basename="service")

urlpatterns = [path("", include(router.urls))]
