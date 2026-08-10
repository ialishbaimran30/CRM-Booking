import React, { useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import AvailableSlotsPanel from '../components/AvailableSlotsPanel';
import { getCurrentUser, isStaffUser } from '../utils/session';

const todayIso = () => new Date().toISOString().substring(0, 10);

export default function AvailableSlotsPage() {
  const isClientPortal = !isStaffUser(getCurrentUser());
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [date, setDate] = useState(searchParams.get('date') || todayIso());

  const bookingsPath = isClientPortal ? '/client-portal/bookings' : '/bookings';
  const waitlistPath = isClientPortal ? '/client-portal/waitlist' : '/waitlist';

  const handleSelectSlot = (startTime, endTime) => {
    const params = new URLSearchParams({ date, start_time: startTime.substring(0, 5), end_time: endTime.substring(0, 5) });
    navigate(`${bookingsPath}?${params.toString()}`);
  };

  return (
    <div className="dashboard-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h1 className="dashboard-title">Available Slots</h1>
          <p className="dashboard-subtitle">See every appointment slot for a day at a glance — always live.</p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <Link to={waitlistPath} className="neu-btn" style={{ background: '#EEF2F9', color: '#3E7BFA', border: 'none', textDecoration: 'none' }}>
            View Waitlist
          </Link>
          <Link to={bookingsPath} className="neu-btn" style={{ background: '#EEF2F9', color: '#6B7A90', border: 'none', textDecoration: 'none' }}>
            Back to Bookings
          </Link>
        </div>
      </div>

      <div className="neu-card" style={{ marginBottom: '24px', padding: '16px', display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
        <div style={{ width: '220px' }}>
          <label style={{ fontSize: '11px', fontWeight: 'bold', color: '#6B7A90', display: 'block', marginBottom: '4px', textTransform: 'uppercase' }}>Date</label>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            style={{ width: '100%', background: '#EEF2F9', border: 'none', borderRadius: '10px', padding: '10px 14px', fontSize: '14px', color: '#1E2A3A', outline: 'none' }}
          />
        </div>
      </div>

      <div className="neu-card" style={{ padding: '16px' }}>
        <AvailableSlotsPanel
          date={date}
          isStaff={!isClientPortal}
          onSelectSlot={handleSelectSlot}
          fullHeight
        />
      </div>
    </div>
  );
}
