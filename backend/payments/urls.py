from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import InvoiceViewSet, PaymentViewSet

app_name = "payments"

router = DefaultRouter()
router.register(r"invoices", InvoiceViewSet, basename="invoice")
router.register(r"payments", PaymentViewSet, basename="payment")

urlpatterns = [
    path('payments/summary/', PaymentViewSet.as_view({'get': 'summary'}), name='payment-summary'),
    path("", include(router.urls)),
]