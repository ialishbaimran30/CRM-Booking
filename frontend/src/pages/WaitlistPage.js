import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { waitlistService } from '../api/waitlistService';
import { notifyApiError } from '../utils/apiError';
import { getCurrentUser, isStaffUser } from '../utils/session';

const formatLabel = (timeStr) => {
  if (!timeStr) return '';
  const [h, m] = timeStr.split(':').map(Number);
  const period = h >= 12 ? 'PM' : 'AM';
  const hour12 = h % 12 === 0 ? 12 : h % 12;
  return `${String(hour12).padStart(2, '0')}:${String(m).padStart(2, '0')} ${period}`;
};

const StatusPill = ({ status }) => {
  const isNotified = status === 'NOTIFIED';
  return (
    <span style={{
      padding: '4px 12px', borderRadius: '20px', fontSize: '12px', fontWeight: '600',
      background: isNotified ? '#DEF7EC' : '#FEF3C7', color: isNotified ? '#03543F' : '#B45309',
    }}>
      {isNotified ? 'Notified — slot was freed' : 'Waiting'}
    </span>
  );
};

export default function WaitlistPage() {
  const isClientPortal = !isStaffUser(getCurrentUser());
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [removingId, setRemovingId] = useState(null);

  const bookingsPath = isClientPortal ? '/client-portal/bookings' : '/bookings';
  const slotsPath = isClientPortal ? '/client-portal/available-slots' : '/bookings/available-slots';

  const fetchEntries = useCallback(async () => {
    try {
      setLoading(true);
      const data = await waitlistService.getWaitlist();
      setEntries(Array.isArray(data) ? data : (data.results || []));
    } catch (err) {
      notifyApiError(err, 'Failed to load the waitlist.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEntries();
  }, [fetchEntries]);

  // Same cross-page sync pattern used throughout the app.
  useEffect(() => {
    const handleStorageSync = (e) => {
      if (e.key === 'payment_sync_timestamp' || e.key === 'booking_sync_timestamp' || !e.key) {
        fetchEntries();
      }
    };
    window.addEventListener('storage', handleStorageSync);

    const interval = setInterval(() => {
      const syncStamp = localStorage.getItem('payment_sync_timestamp');
      if (syncStamp && syncStamp !== window._lastWaitlistSyncStamp) {
        window._lastWaitlistSyncStamp = syncStamp;
        fetchEntries();
      }
    }, 1000);

    return () => {
      window.removeEventListener('storage', handleStorageSync);
      clearInterval(interval);
    };
  }, [fetchEntries]);

  const handleRemove = async (entry) => {
    setRemovingId(entry.id);
    try {
      await waitlistService.leaveWaitlist(entry.id);
      toast.success(isClientPortal ? 'Removed from waitlist.' : 'Client removed from waitlist.');
      localStorage.setItem('payment_sync_timestamp', Date.now().toString());
      setEntries((prev) => prev.filter((e) => e.id !== entry.id));
    } catch (err) {
      notifyApiError(err, 'Failed to remove from the waitlist.');
    } finally {
      setRemovingId(null);
    }
  };

  return (
    <div className="dashboard-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h1 className="dashboard-title">Waitlist</h1>
          <p className="dashboard-subtitle">
            {isClientPortal
              ? 'Slots you\'re waiting on — we\'ll email you the moment one opens up.'
              : 'Everyone waiting on a booked slot, across all clients.'}
          </p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <Link to={slotsPath} className="neu-btn" style={{ background: '#EEF2F9', color: '#3E7BFA', border: 'none', textDecoration: 'none' }}>
            Available Slots
          </Link>
          <Link to={bookingsPath} className="neu-btn" style={{ background: '#EEF2F9', color: '#6B7A90', border: 'none', textDecoration: 'none' }}>
            Back to Bookings
          </Link>
        </div>
      </div>

      <div className="neu-card" style={{ padding: '0', overflow: 'hidden' }}>
        <table className="neu-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              {!isClientPortal && <th style={{ padding: '16px' }}>Client</th>}
              <th style={{ padding: '16px' }}>Date</th>
              <th style={{ padding: '16px' }}>Time Slot</th>
              <th style={{ padding: '16px' }}>Status</th>
              <th style={{ padding: '16px', textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={isClientPortal ? 4 : 5} style={{ textAlign: 'center', padding: '32px', color: '#6B7A90' }}>Loading waitlist...</td></tr>
            ) : entries.length > 0 ? entries.map((entry) => (
              <tr key={entry.id}>
                {!isClientPortal && (
                  <td style={{ padding: '16px', fontWeight: '700', color: '#1E2A3A' }}>
                    {entry.client_full_name} <span style={{ color: '#6B7A90', fontWeight: 400 }}>({entry.client_email})</span>
                  </td>
                )}
                <td style={{ padding: '16px', color: '#6B7A90' }}>{entry.booking_date}</td>
                <td style={{ padding: '16px' }}>{formatLabel(entry.start_time)} - {formatLabel(entry.end_time)}</td>
                <td style={{ padding: '16px' }}><StatusPill status={entry.status} /></td>
                <td style={{ padding: '16px', textAlign: 'right' }}>
                  <button
                    onClick={() => handleRemove(entry)}
                    disabled={removingId === entry.id}
                    style={{ background: '#FDE8E8', color: '#9B1C1C', border: 'none', padding: '6px 14px', borderRadius: '8px', cursor: removingId === entry.id ? 'default' : 'pointer', fontWeight: '600', fontSize: '12px' }}
                  >
                    {removingId === entry.id ? 'Removing...' : (isClientPortal ? 'Cancel' : 'Remove')}
                  </button>
                </td>
              </tr>
            )) : (
              <tr>
                <td colSpan={isClientPortal ? 4 : 5} style={{ textAlign: 'center', padding: '32px', color: '#6B7A90' }}>
                  {isClientPortal ? "You're not waiting on any slots." : 'No one is currently on the waitlist.'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
