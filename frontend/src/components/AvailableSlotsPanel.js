import React, { useEffect, useState, useCallback } from 'react';
import toast from 'react-hot-toast';
import { bookingService } from '../api/bookingService';
import { waitlistService } from '../api/waitlistService';
import { notifyApiError } from '../utils/apiError';

const formatLabel = (timeStr) => {
  const [h, m] = timeStr.split(':').map(Number);
  const period = h >= 12 ? 'PM' : 'AM';
  const hour12 = h % 12 === 0 ? 12 : h % 12;
  return `${String(hour12).padStart(2, '0')}:${String(m).padStart(2, '0')} ${period}`;
};

/**
 * Shows the fixed business-hours slot grid for a date: available vs booked,
 * lets the caller pick an open slot, and offers "Notify me" for a booked
 * one — for clients on their own behalf, or for staff on behalf of the
 * client whose booking they're rescheduling (pass `clientId` for that case).
 * Shared by both the Admin and Client Portal booking forms.
 */
export default function AvailableSlotsPanel({ date, isStaff, clientId, onSelectSlot, fullHeight = false }) {
  const [slots, setSlots] = useState([]);
  const [loading, setLoading] = useState(false);
  const [joiningKey, setJoiningKey] = useState(null);

  const fetchSlots = useCallback(async () => {
    if (!date) return;
    try {
      setLoading(true);
      const data = await bookingService.getAvailableSlots(date);
      setSlots(data?.slots || []);
    } catch (err) {
      notifyApiError(err, 'Failed to load available slots.');
    } finally {
      setLoading(false);
    }
  }, [date]);

  useEffect(() => {
    fetchSlots();
  }, [fetchSlots]);

  // Keep the panel live: refetch whenever any booking/waitlist-affecting
  // action happens elsewhere (same pattern used across the app for sync).
  useEffect(() => {
    const handleStorageSync = (e) => {
      if (e.key === 'payment_sync_timestamp' || e.key === 'booking_sync_timestamp' || !e.key) {
        fetchSlots();
      }
    };
    window.addEventListener('storage', handleStorageSync);

    const interval = setInterval(() => {
      const syncStamp = localStorage.getItem('payment_sync_timestamp');
      if (syncStamp && syncStamp !== window._lastSlotsSyncStamp) {
        window._lastSlotsSyncStamp = syncStamp;
        fetchSlots();
      }
    }, 1000);

    return () => {
      window.removeEventListener('storage', handleStorageSync);
      clearInterval(interval);
    };
  }, [fetchSlots]);

  const handleJoinWaitlist = async (slot) => {
    const key = `${slot.start_time}-${slot.end_time}`;
    setJoiningKey(key);
    try {
      await waitlistService.joinWaitlist({
        booking_date: date,
        start_time: slot.start_time,
        end_time: slot.end_time,
        // Staff have no "own client" to auto-resolve server-side, so when
        // acting on behalf of the client being rescheduled, the target
        // client must be supplied explicitly.
        ...(isStaff && clientId ? { client: clientId } : {}),
      });
      toast.success('Added to waitlist successfully! We\'ll email you if this slot opens up.');
      // Broadcast the same sync signal bookings/payments use so the
      // dedicated Waitlist page and staff's slot view pick this up live.
      localStorage.setItem('payment_sync_timestamp', Date.now().toString());
      fetchSlots();
    } catch (err) {
      notifyApiError(err, 'Failed to join the waitlist.');
    } finally {
      setJoiningKey(null);
    }
  };

  if (!date) {
    return (
      <p style={{ fontSize: '13px', color: '#6B7A90' }}>Pick a date above to see available slots.</p>
    );
  }

  return (
    <div style={{ background: fullHeight ? 'transparent' : '#EEF2F9', borderRadius: '12px', padding: fullHeight ? 0 : '12px', maxHeight: fullHeight ? 'none' : '260px', overflowY: fullHeight ? 'visible' : 'auto' }}>
      {!fullHeight && (
        <p style={{ fontSize: '12px', fontWeight: 'bold', color: '#6B7A90', textTransform: 'uppercase', marginBottom: '8px' }}>
          Available Slots — {date}
        </p>
      )}
      {loading ? (
        <p style={{ fontSize: '13px', color: '#6B7A90' }}>Loading slots...</p>
      ) : slots.length === 0 ? (
        <p style={{ fontSize: '13px', color: '#6B7A90' }}>No slots configured for this date.</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {slots.map((slot) => {
            const key = `${slot.start_time}-${slot.end_time}`;
            return (
              <div
                key={key}
                style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  background: '#fff', borderRadius: '8px', padding: '8px 12px', fontSize: '13px',
                }}
              >
                <div>
                  <strong>{formatLabel(slot.start_time)}</strong>{' '}
                  {slot.available ? (
                    <span style={{ color: '#3FBF8F', fontWeight: 600 }}>✅ Available</span>
                  ) : (
                    <span style={{ color: '#9B1C1C', fontWeight: 600 }}>❌ Booked</span>
                  )}
                  {isStaff && !slot.available && (
                    <span style={{ color: '#6B7A90', marginLeft: '8px' }}>
                      ({slot.client_name}{slot.waitlist_count > 0 ? ` · ${slot.waitlist_count} on waitlist` : ''})
                    </span>
                  )}
                </div>

                {slot.available ? (
                  <button
                    type="button"
                    onClick={() => onSelectSlot(slot.start_time, slot.end_time)}
                    style={{ background: '#3E7BFA', color: '#fff', border: 'none', borderRadius: '8px', padding: '5px 12px', fontSize: '12px', fontWeight: 600, cursor: 'pointer' }}
                  >
                    Select
                  </button>
                ) : (!isStaff || clientId) ? (
                  slot.on_waitlist ? (
                    <span style={{ color: '#6B7A90', fontSize: '12px', fontWeight: 600 }}>✓ On Waitlist</span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => handleJoinWaitlist(slot)}
                      disabled={joiningKey === key}
                      style={{ background: '#EEF2F9', color: '#3E7BFA', border: '1px solid #3E7BFA', borderRadius: '8px', padding: '5px 10px', fontSize: '11px', fontWeight: 600, cursor: joiningKey === key ? 'default' : 'pointer' }}
                    >
                      {joiningKey === key ? 'Joining...' : 'Notify Me When Available'}
                    </button>
                  )
                ) : null}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
