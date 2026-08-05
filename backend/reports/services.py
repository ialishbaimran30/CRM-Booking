from django.db.models import Sum, Count
from django.utils import timezone
from datetime import timedelta
from booking.models import Booking
from clients.models import Client
from payments.models import Invoice


class ReportService:
    """Service layer to handle analytics, metrics, and reporting summaries safely."""

    @staticmethod
    def get_dashboard_summary():
        """Returns overall dashboard metrics."""
        total_bookings = Booking.objects.count()
        
        b_pending = getattr(Booking.BookingStatus, 'PENDING', 'pending')
        b_confirmed = getattr(Booking.BookingStatus, 'CONFIRMED', 'confirmed')
        b_cancelled = getattr(Booking.BookingStatus, 'CANCELLED', 'cancelled')
        
        active_bookings = Booking.objects.filter(status__in=[b_pending, b_confirmed]).count()
        cancelled_bookings = Booking.objects.filter(status=b_cancelled).count()
        
        active_clients = Client.objects.count()
        total_revenue = Invoice.objects.aggregate(total=Sum('total_amount'))['total'] or 0.00

        return {
            "total_bookings": total_bookings,
            "active_bookings": active_bookings,
            "cancelled_bookings": cancelled_bookings,
            "active_clients": active_clients,
            "total_revenue": total_revenue,
        }

    @staticmethod
    def get_periodic_report(period_type="monthly"):
        """Generates accurate periodic reports safely using Python dictionary mapping."""
        now = timezone.now()
        
        if period_type == "daily":
            start_date = now.date()
        elif period_type == "weekly":
            start_date = (now - timedelta(days=7)).date()
        elif period_type == "monthly":
            start_date = (now - timedelta(days=30)).date()
        else:
            start_date = (now - timedelta(days=30)).date()

        # Bookings & Invoices Querysets
        bookings_qs = Booking.objects.all()
        if hasattr(Booking, 'booking_date'):
            bookings_qs = bookings_qs.filter(booking_date__gte=start_date)

        invoices_qs = Invoice.objects.all()
        
        date_field = 'issued_date' if hasattr(Invoice, 'issued_date') else ('created_at' if hasattr(Invoice, 'created_at') else None)
        amount_field = 'total_amount' if hasattr(Invoice, 'total_amount') else 'amount'

        # Bookings Summary Counts
        b_pending = getattr(Booking.BookingStatus, 'PENDING', 'pending')
        b_confirmed = getattr(Booking.BookingStatus, 'CONFIRMED', 'confirmed')
        b_completed = getattr(Booking.BookingStatus, 'COMPLETED', 'completed')
        b_cancelled = getattr(Booking.BookingStatus, 'CANCELLED', 'cancelled')

        total_bookings = bookings_qs.count()
        pending_bookings = bookings_qs.filter(status=b_pending).count() if hasattr(Booking, 'status') else 0
        confirmed_bookings = bookings_qs.filter(status=b_confirmed).count() if hasattr(Booking, 'status') else 0
        completed_bookings = bookings_qs.filter(status=b_completed).count() if hasattr(Booking, 'status') else 0
        cancelled_bookings = bookings_qs.filter(status=b_cancelled).count() if hasattr(Booking, 'status') else 0

        # Revenue Calculation
        total_collected = 0.00
        pending_amount = 0.00
        refunded_amount = 0.00

        for inv in invoices_qs:
            status_val = str(getattr(inv, 'status', '')).upper()
            amt = float(getattr(inv, amount_field, 0) or 0)
            
            if 'PAID' in status_val:
                total_collected += amt
            elif 'PENDING' in status_val or 'UNPAID' in status_val:
                pending_amount += amt
            elif 'REFUNDED' in status_val:
                refunded_amount += amt
            else:
                total_collected += amt

        # New Clients Count
        new_clients_count = Client.objects.count()
        if hasattr(Client, 'created_at'):
            new_clients_count = Client.objects.filter(created_at__date__gte=start_date).count()

        # Cancellation Rate (%)
        cancellation_rate = round((cancelled_bookings / total_bookings * 100), 2) if total_bookings > 0 else 0.00

        # Top Services Ranking
        top_services = []
        try:
            top_services_raw = bookings_qs.values('service__name').annotate(count=Count('id')).order_by('-count')[:4]
            top_services = [{"name": item['service__name'] or "General Service", "count": item['count']} for item in top_services_raw]
        except Exception:
            top_services = []

        # Chart Data Generation
        rev_map = {}
        for inv in invoices_qs:
            if date_field:
                d_val = getattr(inv, date_field, None)
                if d_val:
                    dt_str = d_val.strftime('%b %d')
                    amt = float(getattr(inv, amount_field, 0) or 0)
                    rev_map[dt_str] = rev_map.get(dt_str, 0.0) + amt

        book_map = {}
        booking_date_field = 'booking_date' if hasattr(Booking, 'booking_date') else 'created_at'
        for bk in bookings_qs:
            b_val = getattr(bk, booking_date_field, None)
            if b_val:
                dt_str = b_val.strftime('%b %d')
                book_map[dt_str] = book_map.get(dt_str, 0) + 1

        all_dates = sorted(list(set(list(rev_map.keys()) + list(book_map.keys()))))
        
        chart_data = []
        for dt in all_dates:
            chart_data.append({
                "label": dt,
                "revenue": rev_map.get(dt, 0.0),
                "bookings": book_map.get(dt, 0)
            })

        if not chart_data:
            chart_data = [
                {"label": "Total", "revenue": float(total_collected), "bookings": completed_bookings}
            ]

        return {
            "bookings_summary": {
                "total": total_bookings,
                "pending": pending_bookings,
                "confirmed": confirmed_bookings,
                "completed": completed_bookings,
                "cancelled": cancelled_bookings,
            },
            "revenue_summary": {
                "total_revenue": total_collected,
                "pending_amount": pending_amount,
                "refunded_amount": refunded_amount,
            },
            "top_services": top_services,
            "new_clients_count": new_clients_count,
            "cancellation_rate": cancellation_rate,
            "chart_data": chart_data,
        }