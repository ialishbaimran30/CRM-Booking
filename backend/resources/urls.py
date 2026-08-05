from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import StaffViewSet, ResourceViewSet, BookingAssignmentViewSet

app_name = "resources"

router = DefaultRouter()
router.register("staff", StaffViewSet, basename="staff")
router.register("resources", ResourceViewSet, basename="resource")
router.register("assignments", BookingAssignmentViewSet, basename="assignment")

urlpatterns = [
    path("", include(router.urls)),
]