import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { notificationService } from '../api/notificationService';
import { notifyApiError } from '../utils/apiError';

// Reuses the exact same recipient-scoped /api/notifications/notifications/
// list the bell dropdown uses. Since the Admin is always cc'd on every
// booking-lifecycle event (notifications/services.py::notify_booking_event),
// the Admin's own notification list already IS the complete history — no
// separate history model/endpoint needed.

const ACTION_LABELS = {
  BOOKING_CREATED: { title: 'Booking Created', verb: 'Created by' },
  BOOKING_UPDATED: { title: 'Booking Updated', verb: 'Updated by' },
  BOOKING_RESCHEDULED: { title: 'Booking Rescheduled', verb: 'Rescheduled by' },
  BOOKING_CANCELLATION: { title: 'Booking Cancelled', verb: 'Cancelled by' },
  BOOKING_CONFIRMATION: { title: 'Booking Confirmed', verb: 'By' },
  WAITLIST_SLOT_AVAILABLE: { title: 'Waitlist Slot Available', verb: 'By' },
  REMINDER: { title: 'Reminder', verb: 'By' },
  GENERAL: { title: 'Notification', verb: 'By' },
};

const formatDateTime = (iso) => {
  if (!iso) return '-';
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
};

export default function NotificationHistoryPage() {
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  // Deep link from the notification bell (Topbar.js): ?highlight=<notification id>
  // scrolls to and briefly highlights that specific entry.
  const [searchParams] = useSearchParams();
  const highlightId = searchParams.get('highlight');
  const highlightRef = useRef(null);

  const fetchHistory = useCallback(async () => {
    try {
      setLoading(true);
      const data = await notificationService.getNotifications();
      setNotifications(Array.isArray(data) ? data : (data.results || []));
    } catch (err) {
      notifyApiError(err, 'Failed to load notification history.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  useEffect(() => {
    if (!loading && highlightId && highlightRef.current) {
      highlightRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [loading, highlightId]);

  // Booking-related notifications are the ones with structured actor/booking
  // context — that's what this history is meant to show.
  const bookingEvents = notifications.filter((n) => Object.prototype.hasOwnProperty.call(ACTION_LABELS, n.notification_type));

  const handleMarkRead = async (id) => {
    try {
      await notificationService.markAsRead(id);
      setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
    } catch (err) {
      toast.error('Failed to mark notification as read.');
    }
  };

  if (loading) return <div style={{ padding: '40px', textAlign: 'center', color: '#6B7A90' }}>Loading notification history...</div>;

  return (
    <div className="dashboard-container">
      <div style={{ marginBottom: '24px' }}>
        <h1 className="dashboard-title">Notification History</h1>
        <p className="dashboard-subtitle">Every booking action — who did what, to which booking, and when.</p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {bookingEvents.length === 0 ? (
          <div className="neu-card" style={{ padding: '32px', textAlign: 'center', color: '#6B7A90' }}>
            No booking activity yet.
          </div>
        ) : (
          bookingEvents.map((n) => {
            const meta = ACTION_LABELS[n.notification_type] || ACTION_LABELS.GENERAL;
            const isHighlighted = highlightId && String(n.id) === String(highlightId);
            return (
              <div
                key={n.id}
                ref={isHighlighted ? highlightRef : null}
                className="neu-card"
                onClick={() => !n.is_read && handleMarkRead(n.id)}
                style={{
                  padding: '16px 20px',
                  cursor: n.is_read ? 'default' : 'pointer',
                  borderLeft: n.is_read ? '4px solid transparent' : '4px solid #3E7BFA',
                  boxShadow: isHighlighted ? '0 0 0 2px #3E7BFA' : undefined,
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: '8px' }}>
                  <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#1E2A3A' }}>{meta.title}</h3>
                  <span style={{ fontSize: '12px', color: '#6B7A90' }}>{formatDateTime(n.created_at)}</span>
                </div>
                <div style={{ marginTop: '6px', fontSize: '13px', color: '#374151', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                  {n.client_name && <span><strong>Client:</strong> {n.client_name}</span>}
                  <span><strong>{meta.verb}:</strong> {n.actor_name || n.actor_role || 'System'} {n.actor_role ? `(${n.actor_role})` : ''}</span>
                  {n.booking_id && <span><strong>Booking:</strong> #{n.booking_id}</span>}
                  {(n.previous_value || n.new_value) && (
                    <span>
                      <strong>Previous:</strong> {n.previous_value || '-'} &nbsp;→&nbsp; <strong>New:</strong> {n.new_value || '-'}
                    </span>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
