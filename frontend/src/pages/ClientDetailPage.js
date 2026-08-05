import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { clientService } from '../api/clientService';

export default function ClientDetailPage() {
  const { id } = useParams();
  const [client, setClient] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    clientService.getClientDetail(id)
      .then(data => setClient(data))
      .catch(err => console.error(err))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className="p-8 text-center text-gray-500">Loading client profile...</div>;
  if (!client) return <div className="p-8 text-center text-gray-500">Client not found.</div>;

  return (
    <div className="dashboard-container">
      <Link to="/clients" style={{ color: '#3E7BFA', textDecoration: 'none', fontWeight: '600', display: 'inline-block', marginBottom: '20px' }}>
        &larr; Back to Clients Directory
      </Link>
      
      <div className="neu-card">
        <h1 className="dashboard-title">{client.full_name}</h1>
        <p className="dashboard-subtitle">{client.email} &bull; {client.phone_number || 'No phone number'}</p>
        <p style={{ color: '#6B7A90', fontSize: '12px', marginTop: '4px' }}>{client.city}, {client.country}</p>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <p style={{ color: '#6B7A90', fontSize: '12px', fontWeight: '700', margin: 0 }}>Total Bookings</p>
          <div className="stat-number">{client.total_bookings}</div>
        </div>
        <div className="stat-card">
          <p style={{ color: '#6B7A90', fontSize: '12px', fontWeight: '700', margin: 0 }}>Completed</p>
          <div className="stat-number" style={{ color: '#3FBF8F' }}>{client.total_completed_bookings}</div>
        </div>
        <div className="stat-card">
          <p style={{ color: '#6B7A90', fontSize: '12px', fontWeight: '700', margin: 0 }}>Cancelled</p>
          <div className="stat-number" style={{ color: '#F0563F' }}>{client.total_cancelled_bookings}</div>
        </div>
        <div className="stat-card">
          <p style={{ color: '#6B7A90', fontSize: '12px', fontWeight: '700', margin: 0 }}>Total Paid</p>
          <div className="stat-number" style={{ color: '#3FBF8F' }}>${client.total_amount_paid}</div>
        </div>
      </div>
    </div>
  );
}