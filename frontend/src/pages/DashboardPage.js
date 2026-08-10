import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { clientService } from '../api/clientService';
import { bookingService } from '../api/bookingService';
import { notifyApiError } from '../utils/apiError';

const StatTile = ({ title, value }) => (
  <div className="neu-card" style={{ textAlign: 'center', padding: '20px' }}>
    <p style={{ color: '#6B7A90', fontSize: '12px', textTransform: 'uppercase', fontWeight: '700', margin: 0 }}>{title}</p>
    <p style={{ fontSize: '28px', fontWeight: '800', color: '#3E7BFA', margin: '6px 0 0 0' }}>{value}</p>
  </div>
);

export default function DashboardPage() {
  const [summary, setSummary] = useState({
    total_clients: 0,
    total_bookings: 0,
    pending_bookings: 0,
    confirmed_bookings: 0,
    completed_bookings: 0,
    cancelled_bookings: 0,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        setLoading(true);
        const [clientsRes, bookingsRes] = await Promise.all([
          clientService.getClients(),
          bookingService.getBookings()
        ]);

        const clientsList = Array.isArray(clientsRes) ? clientsRes : (clientsRes.results || []);
        const bookingsList = Array.isArray(bookingsRes) ? bookingsRes : (bookingsRes.results || []);

        const pending = bookingsList.filter(b => b.status === 'Pending' || b.status === 'PENDING').length;
        const confirmed = bookingsList.filter(b => b.status === 'Confirmed' || b.status === 'CONFIRMED').length;
        const completedList = bookingsList.filter(b => b.status === 'Completed' || b.status === 'COMPLETED');
        const cancelled = bookingsList.filter(b => b.status === 'Cancelled' || b.status === 'CANCELLED').length;

        setSummary({
          total_clients: clientsList.length,
          total_bookings: bookingsList.length,
          pending_bookings: pending,
          confirmed_bookings: confirmed,
          completed_bookings: completedList.length,
          cancelled_bookings: cancelled,
        });
      } catch (err) {
        console.error("Error fetching dashboard stats:", err);
        notifyApiError(err, "Failed to load dashboard data.");
      } finally {
        setLoading(false);
      }
    };

    fetchDashboardData();
  }, []);

  if (loading) return <div style={{ padding: '40px', textAlign: 'center', color: '#6B7A90' }}>Loading dashboard...</div>;

  return (
    <div className="dashboard-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px' }}>
        <div>
          <h1 className="dashboard-title">Dashboard</h1>
          <p className="dashboard-subtitle">An overview of your business performance.</p>
        </div>
      </div>

      <div className="stats-grid">
        <StatTile title="Total Clients" value={summary.total_clients} />
        <StatTile title="Total Bookings" value={summary.total_bookings} />
        <StatTile title="Completed Bookings" value={summary.completed_bookings} />
      </div>
    </div>
  );
}