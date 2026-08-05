import React, { useState, useEffect } from 'react';
import { bookingService } from '../api/bookingService';
import { clientService } from '../api/clientService';
import toast from 'react-hot-toast';

const StatusBadge = ({ status }) => {
  const statusStyles = {
    PENDING: { background: '#FEF3C7', color: '#B45309' },
    CONFIRMED: { background: '#E0E7FF', color: '#3E7BFA' },
    COMPLETED: { background: '#DEF7EC', color: '#03543F' },
    CANCELLED: { background: '#FDE8E8', color: '#9B1C1C' },
  };
  
  const currentStyle = statusStyles[status?.toUpperCase()] || { background: '#F3F4F6', color: '#374151' };

  return (
    <span style={{ padding: '4px 12px', borderRadius: '20px', fontSize: '12px', fontWeight: '600', ...currentStyle }}>
      {status || 'Pending'}
    </span>
  );
};

const PaymentStatusBadge = ({ status }) => {
  const paymentStyles = {
    PAID: { background: '#DEF7EC', color: '#03543F' },
    PENDING: { background: '#FEF3C7', color: '#B45309' },
    REFUNDED: { background: '#FDE8E8', color: '#9B1C1C' },
  };
  
  const currentStyle = paymentStyles[status?.toUpperCase()] || { background: '#F3F4F6', color: '#374151' };

  return (
    <span style={{ padding: '4px 12px', borderRadius: '20px', fontSize: '12px', fontWeight: '600', ...currentStyle }}>
      {status || 'Pending'}
    </span>
  );
};

export default function BookingListPage() {
  const [bookings, setBookings] = useState([]);
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Search & Filter States
  const [searchQuery, setSearchQuery] = useState('');
  const [filterDate, setFilterDate] = useState('');

  const [showModal, setShowModal] = useState(false);
  const [selectedBooking, setSelectedBooking] = useState(null);
  const [isEditing, setIsEditing] = useState(false);

  const [formData, setFormData] = useState({
    client: '',
    service_name: '',
    booking_date: '',
    start_time: '10:00',
    end_time: '11:00',
    price: '',
    payment_status: 'PENDING',
    notes: '',
  });

  const formatTimeForInput = (timeStr) => {
    if (!timeStr) return '10:00';
    return timeStr.substring(0, 5);
  };

  const fetchData = async () => {
    try {
      setLoading(true);
      const [bookingData, clientData] = await Promise.all([
        bookingService.getBookings(),
        clientService.getClients()
      ]);

      let bookingsArray = [];
      if (Array.isArray(bookingData)) {
        bookingsArray = bookingData;
      } else if (bookingData && Array.isArray(bookingData.results)) {
        bookingsArray = bookingData.results;
      } else if (bookingData && Array.isArray(bookingData.data)) {
        bookingsArray = bookingData.data;
      }

      let clientsArray = [];
      if (Array.isArray(clientData)) {
        clientsArray = clientData;
      } else if (clientData && Array.isArray(clientData.results)) {
        clientsArray = clientData.results;
      }

      setBookings(bookingsArray);
      setClients(clientsArray);
    } catch (err) {
      setError('Failed to fetch bookings.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleServiceNameChange = (value, isEditMode = false) => {
    if (value.length > 255) {
      toast.error("Service name cannot exceed 255 characters!");
      return;
    }
    if (isEditMode) {
      setSelectedBooking({...selectedBooking, service_name: value});
    } else {
      setFormData({...formData, service_name: value});
    }
  };

  const handleCreateBooking = async (e) => {
    e.preventDefault();
    if (formData.service_name.length > 255) {
      toast.error("Ensure this field has no more than 255 characters.");
      return;
    }
    try {
      const payload = {
        ...formData,
        client: parseInt(formData.client, 10),
        start_time: formData.start_time.length === 5 ? `${formData.start_time}:00` : formData.start_time,
        end_time: formData.end_time.length === 5 ? `${formData.end_time}:00` : formData.end_time,
      };

      await bookingService.createBooking(payload);
      setShowModal(false);
      setFormData({
        client: '',
        service_name: '',
        booking_date: '',
        start_time: '10:00',
        end_time: '11:00',
        price: '',
        payment_status: 'PENDING',
        notes: '',
      });
      toast.success("Booking created successfully!");
      
      // Trigger cross-module sync flag for payments tab
      localStorage.setItem('payment_sync_timestamp', Date.now().toString());
      
      fetchData();
    } catch (err) {
      const errorData = err.response?.data;
      if (errorData?.service_name) {
        toast.error(errorData.service_name[0]);
      } else {
        toast.error("Failed to create booking.");
      }
      console.error("Booking Creation Error:", errorData || err);
    }
  };

  const handleUpdateBooking = async (e) => {
    e.preventDefault();
    if (selectedBooking.service_name?.length > 255) {
      toast.error("Ensure this field has no more than 255 characters.");
      return;
    }
    try {
      const bookingId = selectedBooking.id || selectedBooking.pk;
      if (!bookingId) {
        toast.error("Error: Booking ID not found!");
        return;
      }

      const formattedStartTime = selectedBooking.start_time?.length === 5 ? `${selectedBooking.start_time}:00` : selectedBooking.start_time;
      const formattedEndTime = selectedBooking.end_time?.length === 5 ? `${selectedBooking.end_time}:00` : selectedBooking.end_time;

      const payload = {
        service_name: selectedBooking.service_name,
        booking_date: selectedBooking.booking_date,
        start_time: formattedStartTime,
        end_time: formattedEndTime,
        status: selectedBooking.status,
        payment_status: selectedBooking.payment_status,
        price: selectedBooking.price !== '' ? parseFloat(selectedBooking.price) : null,
        notes: selectedBooking.notes || '',
      };

      await bookingService.updateBooking(bookingId, payload);

      toast.success("Booking updated successfully!");
      setIsEditing(false);
      setSelectedBooking(null);
      fetchData();
    } catch (err) {
      const errorData = err.response?.data;
      if (errorData?.service_name) {
        toast.error(errorData.service_name[0]);
      } else {
        toast.error("Failed to update booking.");
      }
      console.error("Update Error:", errorData || err);
    }
  };

  const handleDeleteBooking = async (bookingObj) => {
    const bookingId = bookingObj?.id || bookingObj?.pk;
    if (!bookingId) {
      toast.error("Error: Booking ID missing for deletion.");
      return;
    }

    try {
      await bookingService.deleteBooking(bookingId);
      toast.success("Booking deleted successfully!");
      
      // Update local state instantly without waiting for refetch
      setBookings(prevBookings => prevBookings.filter(b => (b.id || b.pk) !== bookingId));
      setSelectedBooking(null);
      
      // Signal cross-module payment sync timestamp
      localStorage.setItem('payment_sync_timestamp', Date.now().toString());
      
      fetchData();
    } catch (err) {
      toast.error("Failed to delete booking from server.");
      console.error("Delete Error:", err.response?.data || err);
    }
  };

  const filteredBookings = bookings.filter((booking) => {
    const clientName = (booking.client_full_name || booking.client_name || booking.client?.full_name || '').toLowerCase();
    const serviceName = (booking.service_name || '').toLowerCase();
    const query = searchQuery.toLowerCase();

    const matchesSearch = clientName.includes(query) || serviceName.includes(query);
    const matchesDate = filterDate ? booking.booking_date === filterDate : true;

    return matchesSearch && matchesDate;
  });

  if (loading) return <div style={{ padding: '40px', textAlign: 'center', color: '#6B7A90' }}>Loading bookings...</div>;
  if (error) return <div style={{ padding: '40px', textAlign: 'center', color: '#F0563F' }}>{error}</div>;

  return (
    <div className="dashboard-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px' }}>
        <div>
          <h1 className="dashboard-title">Bookings</h1>
          <p className="dashboard-subtitle">Manage all client appointments.</p>
        </div>
        <button 
          onClick={() => setShowModal(true)} 
          className="neu-btn neu-btn-primary" 
          style={{ border: 'none', cursor: 'pointer' }}
        >
          + New Booking
        </button>
      </div>

      <div className="neu-card" style={{ marginBottom: '24px', padding: '16px', display: 'flex', gap: '16px', flexWrap: 'wrap', alignItems: 'center' }}>
        <div style={{ flex: 1, minWidth: '240px' }}>
          <label style={{ fontSize: '11px', fontWeight: 'bold', color: '#6B7A90', display: 'block', marginBottom: '4px', textTransform: 'uppercase' }}>Search by Client or Service</label>
          <input 
            type="text" 
            placeholder="Type client name or service..." 
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ width: '100%', background: '#EEF2F9', border: 'none', borderRadius: '10px', padding: '10px 14px', fontSize: '14px', color: '#1E2A3A', outline: 'none' }}
          />
        </div>
        <div style={{ width: '200px' }}>
          <label style={{ fontSize: '11px', fontWeight: 'bold', color: '#6B7A90', display: 'block', marginBottom: '4px', textTransform: 'uppercase' }}>Filter by Date</label>
          <input 
            type="date" 
            value={filterDate}
            onChange={(e) => setFilterDate(e.target.value)}
            style={{ width: '100%', background: '#EEF2F9', border: 'none', borderRadius: '10px', padding: '10px 14px', fontSize: '14px', color: '#1E2A3A', outline: 'none' }}
          />
        </div>
        {filterDate && (
          <div style={{ alignSelf: 'flex-end', paddingBottom: '2px' }}>
            <button 
              onClick={() => setFilterDate('')} 
              style={{ background: 'transparent', border: 'none', color: '#3E7BFA', fontSize: '13px', cursor: 'pointer', fontWeight: '600' }}
            >
              Clear Date
            </button>
          </div>
        )}
      </div>

      <div className="neu-card" style={{ padding: '0', overflow: 'hidden' }}>
        <table className="neu-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <th style={{ padding: '16px' }}>Client</th>
              <th style={{ padding: '16px' }}>Service</th>
              <th style={{ padding: '16px' }}>Date</th>
              <th style={{ padding: '16px' }}>Status</th>
              <th style={{ padding: '16px' }}>Payment</th>
              <th style={{ padding: '16px', textAlign: 'right' }}>Amount</th>
              <th style={{ padding: '16px', textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredBookings.length > 0 ? filteredBookings.map((booking) => (
              <tr key={booking.id || booking.pk}>
                <td style={{ padding: '16px', fontWeight: '700', color: '#1E2A3A' }}>
                  {booking.client_full_name || booking.client_name || booking.client?.full_name || `Client #${booking.client}`}
                </td>
                <td style={{ padding: '16px' }}>{booking.service_name || booking.service}</td>
                <td style={{ padding: '16px', color: '#6B7A90' }}>{booking.booking_date || booking.date}</td>
                <td style={{ padding: '16px' }}><StatusBadge status={booking.status} /></td>
                <td style={{ padding: '16px' }}><PaymentStatusBadge status={booking.payment_status} /></td>
                <td style={{ padding: '16px', textAlign: 'right', fontWeight: '700', color: '#1E2A3A' }}>
                  ${typeof booking.price === 'number' ? booking.price.toFixed(2) : (booking.price || booking.amount || '0.00')}
                </td>
                <td style={{ padding: '16px', textAlign: 'right' }}>
                  <button 
                    onClick={() => { setSelectedBooking(booking); setIsEditing(false); }} 
                    className="neu-btn" 
                    style={{ padding: '6px 12px', fontSize: '12px', cursor: 'pointer', border: 'none', background: '#EEF2F9' }}
                  >
                    Details
                  </button>
                </td>
              </tr>
            )) : (
              <tr>
                <td colSpan="7" style={{ textAlign: 'center', padding: '32px', color: '#6B7A90' }}>No bookings found.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* CREATE NEW BOOKING MODAL */}
      {showModal && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(30, 42, 58, 0.4)', display: 'flex', justifyContent: 'center', alignItems: 'center', zIndex: 1000 }}>
          <div style={{ background: '#F4F7FC', padding: '24px', borderRadius: '16px', width: '100%', maxWidth: '500px', boxShadow: '0 8px 30px rgba(0, 0, 0, 0.12)' }}>
            <h2 style={{ marginBottom: '16px', color: '#1E2A3A' }}>Create New Booking</h2>
            <form onSubmit={handleCreateBooking} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div>
                <label style={{ fontSize: '12px', fontWeight: 'bold', color: '#6B7A90', textTransform: 'uppercase', display: 'block', marginBottom: '6px' }}>Select Client *</label>
                <select 
                  required
                  value={formData.client}
                  onChange={(e) => setFormData({...formData, client: e.target.value})}
                  style={{ width: '100%', background: '#EEF2F9', border: 'none', borderRadius: '12px', padding: '10px', fontSize: '14px', color: '#1E2A3A', outline: 'none' }}
                >
                  <option value="">-- Select a Client --</option>
                  {clients.map(c => (
                    <option key={c.id || c.pk} value={c.id || c.pk}>{c.full_name || c.name} ({c.email})</option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ fontSize: '12px', fontWeight: 'bold', color: '#6B7A90', textTransform: 'uppercase', display: 'block', marginBottom: '6px' }}>Service Name * (Max 255 chars)</label>
                <input 
                  type="text" 
                  required 
                  maxLength={255}
                  placeholder="e.g. Consultation / Therapy Session"
                  value={formData.service_name} 
                  onChange={(e) => handleServiceNameChange(e.target.value, false)} 
                  style={{ width: '100%', background: '#EEF2F9', border: 'none', borderRadius: '12px', padding: '10px', fontSize: '14px', color: '#1E2A3A', outline: 'none' }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div>
                  <label style={{ fontSize: '12px', fontWeight: 'bold', color: '#6B7A90', textTransform: 'uppercase', display: 'block', marginBottom: '6px' }}>Date *</label>
                  <input 
                    type="date" 
                    required 
                    value={formData.booking_date} 
                    onChange={(e) => setFormData({...formData, booking_date: e.target.value})} 
                    style={{ width: '100%', background: '#EEF2F9', border: 'none', borderRadius: '12px', padding: '10px', fontSize: '14px', color: '#1E2A3A', outline: 'none' }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: '12px', fontWeight: 'bold', color: '#6B7A90', textTransform: 'uppercase', display: 'block', marginBottom: '6px' }}>Price ($) *</label>
                  <input 
                    type="number" 
                    step="0.01"
                    required 
                    placeholder="0.00"
                    value={formData.price} 
                    onChange={(e) => setFormData({...formData, price: e.target.value})} 
                    style={{ width: '100%', background: '#EEF2F9', border: 'none', borderRadius: '12px', padding: '10px', fontSize: '14px', color: '#1E2A3A', outline: 'none' }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div>
                  <label style={{ fontSize: '12px', fontWeight: 'bold', color: '#6B7A90', textTransform: 'uppercase', display: 'block', marginBottom: '6px' }}>Payment Status *</label>
                  <select 
                    value={formData.payment_status}
                    onChange={(e) => setFormData({...formData, payment_status: e.target.value})}
                    style={{ width: '100%', background: '#EEF2F9', border: 'none', borderRadius: '12px', padding: '10px', fontSize: '14px', color: '#1E2A3A', outline: 'none' }}
                  >
                    <option value="PENDING">Pending</option>
                    <option value="PAID">Paid</option>
                    <option value="REFUNDED">Refunded</option>
                  </select>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div>
                  <label style={{ fontSize: '12px', fontWeight: 'bold', color: '#6B7A90', textTransform: 'uppercase', display: 'block', marginBottom: '6px' }}>Start Time *</label>
                  <input 
                    type="time" 
                    required 
                    value={formData.start_time} 
                    onChange={(e) => setFormData({...formData, start_time: e.target.value})} 
                    style={{ width: '100%', background: '#EEF2F9', border: 'none', borderRadius: '12px', padding: '10px', fontSize: '14px', color: '#1E2A3A', outline: 'none' }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: '12px', fontWeight: 'bold', color: '#6B7A90', textTransform: 'uppercase', display: 'block', marginBottom: '6px' }}>End Time *</label>
                  <input 
                    type="time" 
                    required 
                    value={formData.end_time} 
                    onChange={(e) => setFormData({...formData, end_time: e.target.value})} 
                    style={{ width: '100%', background: '#EEF2F9', border: 'none', borderRadius: '12px', padding: '10px', fontSize: '14px', color: '#1E2A3A', outline: 'none' }}
                  />
                </div>
              </div>

              <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', marginTop: '12px' }}>
                <button 
                  type="button" 
                  onClick={() => setShowModal(false)} 
                  className="neu-btn"
                  style={{ background: '#EEF2F9', color: '#6B7A90', border: 'none', cursor: 'pointer' }}
                >
                  Cancel
                </button>
                <button 
                  type="submit" 
                  className="neu-btn neu-btn-primary"
                  style={{ border: 'none', cursor: 'pointer' }}
                >
                  Save Booking
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* DETAILS & EDIT / STATUS CHANGE MODAL */}
      {selectedBooking && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(30, 42, 58, 0.4)', display: 'flex', justifyContent: 'center', alignItems: 'center', zIndex: 1000 }}>
          <div style={{ background: '#F4F7FC', padding: '24px', borderRadius: '16px', width: '100%', maxWidth: '500px', boxShadow: '0 8px 30px rgba(0, 0, 0, 0.12)', maxHeight: '90vh', overflowY: 'auto' }}>
            <h2 style={{ marginBottom: '16px', color: '#1E2A3A' }}>
              {isEditing ? 'Edit Booking' : 'Booking Details'}
            </h2>

            {!isEditing ? (
              // VIEW DETAILS MODE
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', color: '#1E2A3A' }}>
                <p><strong>Client:</strong> {selectedBooking.client_full_name || selectedBooking.client_name || `Client #${selectedBooking.client}`}</p>
                <p><strong>Service:</strong> {selectedBooking.service_name}</p>
                <p><strong>Date:</strong> {selectedBooking.booking_date}</p>
                <p><strong>Time:</strong> {formatTimeForInput(selectedBooking.start_time)} - {formatTimeForInput(selectedBooking.end_time)}</p>
                <p><strong>Price:</strong> ${selectedBooking.price}</p>
                <p><strong>Status:</strong> <StatusBadge status={selectedBooking.status} /></p>
                <p><strong>Payment Status:</strong> <PaymentStatusBadge status={selectedBooking.payment_status} /></p>
                <p><strong>Notes:</strong> {selectedBooking.notes || 'None'}</p>

                <div style={{ display: 'flex', gap: '10px', marginTop: '16px', justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                  <button onClick={() => setIsEditing(true)} className="neu-btn neu-btn-primary" style={{ border: 'none', cursor: 'pointer' }}>Edit / Change Status</button>
                  <button 
                    onClick={() => handleDeleteBooking(selectedBooking)} 
                    style={{ background: '#FDE8E8', color: '#9B1C1C', border: 'none', padding: '8px 16px', borderRadius: '8px', cursor: 'pointer', fontWeight: '600' }}
                  >
                    Delete
                  </button>
                  <button onClick={() => setSelectedBooking(null)} className="neu-btn" style={{ background: '#EEF2F9', border: 'none', cursor: 'pointer' }}>Close</button>
                </div>
              </div>
            ) : (
              // EDIT / STATUS CHANGE FORM MODE
              <form onSubmit={handleUpdateBooking} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div>
                  <label style={{ fontSize: '12px', fontWeight: 'bold', color: '#6B7A90', display: 'block', marginBottom: '4px' }}>Service Name (Max 255 chars)</label>
                  <input 
                    type="text" 
                    maxLength={255}
                    value={selectedBooking.service_name || ''} 
                    onChange={(e) => handleServiceNameChange(e.target.value, true)}
                    style={{ width: '100%', background: '#EEF2F9', border: 'none', borderRadius: '8px', padding: '8px', outline: 'none' }}
                  />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: 'bold', color: '#6B7A90', display: 'block', marginBottom: '4px' }}>Booking Status</label>
                    <select 
                      value={selectedBooking.status || 'PENDING'} 
                      onChange={(e) => setSelectedBooking({...selectedBooking, status: e.target.value})}
                      style={{ width: '100%', background: '#EEF2F9', border: 'none', borderRadius: '8px', padding: '8px', outline: 'none' }}
                    >
                      <option value="PENDING">Pending</option>
                      <option value="CONFIRMED">Confirmed</option>
                      <option value="COMPLETED">Completed</option>
                      <option value="CANCELLED">Cancelled</option>
                    </select>
                  </div>

                  <div>
                    <label style={{ fontSize: '12px', fontWeight: 'bold', color: '#6B7A90', display: 'block', marginBottom: '4px' }}>Payment Status</label>
                    <select 
                      value={selectedBooking.payment_status || 'PENDING'} 
                      onChange={(e) => setSelectedBooking({...selectedBooking, payment_status: e.target.value})}
                      style={{ width: '100%', background: '#EEF2F9', border: 'none', borderRadius: '8px', padding: '8px', outline: 'none' }}
                    >
                      <option value="PENDING">Pending</option>
                      <option value="PAID">Paid</option>
                      <option value="REFUNDED">Refunded</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label style={{ fontSize: '12px', fontWeight: 'bold', color: '#6B7A90', display: 'block', marginBottom: '4px' }}>Date</label>
                  <input 
                    type="date" 
                    value={selectedBooking.booking_date || ''} 
                    onChange={(e) => setSelectedBooking({...selectedBooking, booking_date: e.target.value})}
                    style={{ width: '100%', background: '#EEF2F9', border: 'none', borderRadius: '8px', padding: '8px', outline: 'none' }}
                  />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: 'bold', color: '#6B7A90', display: 'block', marginBottom: '4px' }}>Start Time</label>
                    <input 
                      type="time" 
                      value={formatTimeForInput(selectedBooking.start_time)} 
                      onChange={(e) => setSelectedBooking({...selectedBooking, start_time: e.target.value})}
                      style={{ width: '100%', background: '#EEF2F9', border: 'none', borderRadius: '8px', padding: '8px', outline: 'none' }}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: 'bold', color: '#6B7A90', display: 'block', marginBottom: '4px' }}>End Time</label>
                    <input 
                      type="time" 
                      value={formatTimeForInput(selectedBooking.end_time)} 
                      onChange={(e) => setSelectedBooking({...selectedBooking, end_time: e.target.value})}
                      style={{ width: '100%', background: '#EEF2F9', border: 'none', borderRadius: '8px', padding: '8px', outline: 'none' }}
                    />
                  </div>
                </div>

                <div>
                  <label style={{ fontSize: '12px', fontWeight: 'bold', color: '#6B7A90', display: 'block', marginBottom: '4px' }}>Price ($)</label>
                  <input 
                    type="number" 
                    step="0.01"
                    value={selectedBooking.price || ''} 
                    onChange={(e) => setSelectedBooking({...selectedBooking, price: e.target.value})}
                    style={{ width: '100%', background: '#EEF2F9', border: 'none', borderRadius: '8px', padding: '8px', outline: 'none' }}
                  />
                </div>

                <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '12px' }}>
                  <button type="button" onClick={() => setIsEditing(false)} className="neu-btn" style={{ background: '#EEF2F9', border: 'none', cursor: 'pointer' }}>Cancel</button>
                  <button type="submit" className="neu-btn neu-btn-primary" style={{ border: 'none', cursor: 'pointer' }}>Save Changes</button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}