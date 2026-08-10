import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { bookingService } from '../api/bookingService';
import { clientService } from '../api/clientService';
import AvailableSlotsPanel from '../components/AvailableSlotsPanel';
import toast from 'react-hot-toast';
import { notifyApiError } from '../utils/apiError';
import { getCurrentUser, isStaffUser } from '../utils/session';

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
  const isClientPortal = !isStaffUser(getCurrentUser());
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const slotsPagePath = isClientPortal ? '/client-portal/available-slots' : '/bookings/available-slots';

  const [bookings, setBookings] = useState([]);
  const [clients, setClients] = useState([]);
  const [services, setServices] = useState([]);
  const [myClient, setMyClient] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Search & Filter States
  const [searchQuery, setSearchQuery] = useState('');
  const [filterDate, setFilterDate] = useState('');

  const [showModal, setShowModal] = useState(false);
  const [selectedBooking, setSelectedBooking] = useState(null);
  const [isEditing, setIsEditing] = useState(false);
  const [serviceTouched, setServiceTouched] = useState(false);
  const [showEditSlots, setShowEditSlots] = useState(false);
  const [bookingViaSlotLink, setBookingViaSlotLink] = useState(false);

  const [formData, setFormData] = useState({
    client: '',
    service: '',
    booking_date: '',
    start_time: '10:00',
    end_time: '11:00',
    notes: '',
  });

  const formatTimeForInput = (timeStr) => {
    if (!timeStr) return '10:00';
    return timeStr.substring(0, 5);
  };

  // Client-side estimate only — purely informational. The backend always
  // recalculates and validates the real total from the Service's hourly
  // rate before saving; this preview just mirrors that math for display.
  const estimatePrice = (serviceId, startTime, endTime) => {
    const service = services.find((s) => String(s.id) === String(serviceId));
    if (!service || !startTime || !endTime) return null;
    const [sh, sm] = startTime.split(':').map(Number);
    const [eh, em] = endTime.split(':').map(Number);
    const durationHours = (eh * 60 + em - (sh * 60 + sm)) / 60;
    if (!(durationHours > 0)) return null;
    const rate = parseFloat(service.hourly_rate);
    return { service, durationHours, rate, total: durationHours * rate };
  };

  const fetchData = async () => {
    try {
      setLoading(true);
      // The Clients list (/api/clients/) is a Staff-only CRM endpoint — Clients
      // are correctly denied access to it, so only fetch it in staff mode.
      // In the Client Portal, `myClient` (their own record) is what's needed instead.
      const [bookingData, clientData, myClientData, serviceData] = await Promise.all([
        bookingService.getBookings(),
        isClientPortal ? Promise.resolve([]) : clientService.getClients(),
        isClientPortal ? clientService.getMyClient() : Promise.resolve(null),
        bookingService.getServices(),
      ]);

      if (myClientData) {
        setMyClient(myClientData);
      }
      setServices(Array.isArray(serviceData) ? serviceData : (serviceData?.results || []));

      let rawBookings = [];
      if (Array.isArray(bookingData)) {
        rawBookings = bookingData;
      } else if (bookingData && Array.isArray(bookingData.results)) {
        rawBookings = bookingData.results;
      } else if (bookingData && Array.isArray(bookingData.data)) {
        rawBookings = bookingData.data;
      }

      // Deduplicate bookings based on id or pk to prevent duplicate key errors during pagination/search
      const uniqueBookingsMap = new Map();
      rawBookings.forEach(b => {
        const uniqueId = b.id || b.pk;
        if (uniqueId !== undefined && uniqueId !== null) {
          uniqueBookingsMap.set(uniqueId, b);
        } else {
          uniqueBookingsMap.set(Math.random(), b);
        }
      });

      let rawClients = [];
      if (Array.isArray(clientData)) {
        rawClients = clientData;
      } else if (clientData && Array.isArray(clientData.results)) {
        rawClients = clientData.results;
      }

      const uniqueClientsMap = new Map();
      rawClients.forEach(c => {
        const uniqueId = c.id || c.pk;
        if (uniqueId !== undefined && uniqueId !== null) {
          uniqueClientsMap.set(uniqueId, c);
        }
      });

      setBookings(Array.from(uniqueBookingsMap.values()));
      setClients(Array.from(uniqueClientsMap.values()));
    } catch (err) {
      setError('Failed to fetch bookings.');
      console.error(err);
      notifyApiError(err, 'Failed to fetch bookings.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  // Real-time sync: pick up bookings created/updated/deleted from another
  // tab (e.g. Admin CRM and Client Portal open side by side) without a manual refresh.
  useEffect(() => {
    const handleStorageSync = (e) => {
      if (
        e.key === 'payment_sync_timestamp' ||
        e.key === 'booking_sync_timestamp' ||
        !e.key
      ) {
        fetchData();
      }
    };

    window.addEventListener('storage', handleStorageSync);

    const interval = setInterval(() => {
      const syncStamp = localStorage.getItem('payment_sync_timestamp');
      if (syncStamp && syncStamp !== window._lastBookingSyncStamp) {
        window._lastBookingSyncStamp = syncStamp;
        fetchData();
      }
    }, 1000);

    return () => {
      window.removeEventListener('storage', handleStorageSync);
      clearInterval(interval);
    };
  }, []);

  // Deep link carrying a preselected date/time — either a "Book Now" link
  // from a waitlist-availability email, or "Select" on the dedicated
  // Available Slots page. Preselect it and open the create form right away.
  useEffect(() => {
    const date = searchParams.get('date');
    const startTime = searchParams.get('start_time');
    const endTime = searchParams.get('end_time');
    if (date && startTime && endTime) {
      setFormData((prev) => ({ ...prev, booking_date: date, start_time: startTime, end_time: endTime }));
      setBookingViaSlotLink(true);
      setShowModal(true);
      setSearchParams({}, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCreateBooking = async (e) => {
    e.preventDefault();
    if (!formData.service) {
      toast.error("Select a service to book.");
      return;
    }
    if (isClientPortal && !myClient) {
      toast.error("Your account isn't ready yet, please try again in a moment.");
      return;
    }
    try {
      const payload = {
        service: parseInt(formData.service, 10),
        booking_date: formData.booking_date,
        notes: formData.notes,
        // Clients can only ever book for themselves; ignore whatever the form holds.
        client: isClientPortal ? myClient.id : parseInt(formData.client, 10),
        start_time: formData.start_time.length === 5 ? `${formData.start_time}:00` : formData.start_time,
        end_time: formData.end_time.length === 5 ? `${formData.end_time}:00` : formData.end_time,
        // Note: price/rate/payment_status are never sent — the backend always
        // calculates and validates them from the selected Service.
      };

      const created = await bookingService.createBooking(payload);
      setShowModal(false);
      setFormData({
        client: '',
        service: '',
        booking_date: '',
        start_time: '10:00',
        end_time: '11:00',
        notes: '',
      });
      toast.success(bookingViaSlotLink ? "Slot booked successfully!" : "Booking created successfully!");
      setBookingViaSlotLink(false);
      if (created?.email_sent === true) {
        toast.success("Confirmation email sent to the client.");
      } else if (created?.email_sent === false) {
        toast.error("Booking created, but the confirmation email could not be sent.");
      }

      localStorage.setItem('payment_sync_timestamp', Date.now().toString());
      fetchData();
    } catch (err) {
      console.error("Booking Creation Error:", err.response?.data || err);
      notifyApiError(err, "Failed to create booking.");
    }
  };

  const handleUpdateBooking = async (e) => {
    e.preventDefault();
    try {
      const bookingId = selectedBooking.id || selectedBooking.pk;
      if (!bookingId) {
        toast.error("Error: Booking ID not found!");
        return;
      }

      const formattedStartTime = selectedBooking.start_time?.length === 5 ? `${selectedBooking.start_time}:00` : selectedBooking.start_time;
      const formattedEndTime = selectedBooking.end_time?.length === 5 ? `${selectedBooking.end_time}:00` : selectedBooking.end_time;

      const payload = {
        booking_date: selectedBooking.booking_date,
        start_time: formattedStartTime,
        end_time: formattedEndTime,
        status: selectedBooking.status,
        notes: selectedBooking.notes || '',
        // Only include `service` if the dropdown was actually touched — the
        // backend takes a fresh rate snapshot whenever `service` is present
        // in the payload, and otherwise keeps the original locked-in rate
        // for this booking even if the Service's live rate has since changed.
        ...(serviceTouched ? { service: selectedBooking.service ? parseInt(selectedBooking.service, 10) : null } : {}),
        // price/rate_snapshot/payment_status are never sent — backend-owned.
      };

      const updated = await bookingService.updateBooking(bookingId, payload);

      toast.success("Booking updated successfully!");
      if (updated?.client_notification_sent === true) {
        toast.success("Confirmation email sent to the client.");
      } else if (updated?.client_notification_sent === false) {
        toast.error("Booking updated, but the confirmation email could not be sent.");
      }
      if (updated?.waitlist_notified_count > 0) {
        toast.success(`Notification email sent to ${updated.waitlist_notified_count} waiting client(s).`);
      }
      setIsEditing(false);
      setServiceTouched(false);
      setSelectedBooking(null);
      setShowEditSlots(false);
      localStorage.setItem('payment_sync_timestamp', Date.now().toString());
      fetchData();
    } catch (err) {
      console.error("Update Error:", err.response?.data || err);
      notifyApiError(err, "Failed to update booking.");
      if (selectedBooking?.booking_date) {
        setShowEditSlots(true);
      }
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

      setBookings(prevBookings => prevBookings.filter(b => (b.id || b.pk) !== bookingId));
      setSelectedBooking(null);

      localStorage.setItem('payment_sync_timestamp', Date.now().toString());

      fetchData();
    } catch (err) {
      console.error("Delete Error:", err.response?.data || err);
      notifyApiError(err, "Failed to delete booking.");
    }
  };

  const filteredBookings = bookings.filter((booking) => {
    const clientName = (booking.client_full_name || booking.client_name || booking.client?.full_name || '').toLowerCase();
    const serviceName = (booking.service_name || '').toLowerCase();
    const query = searchQuery.toLowerCase();

    const matchesSearch = clientName.includes(query) || serviceName.includes(query);
    
    // Normalize and compare booking_date cleanly to include end dates and boundary filters accurately
    let matchesDate = true;
    if (filterDate) {
      const bookingDateStr = booking.booking_date || booking.date;
      if (bookingDateStr) {
        // Compare ISO strings or standard date format segments (YYYY-MM-DD)
        const normalizedBookingDate = bookingDateStr.substring(0, 10);
        const normalizedFilterDate = filterDate.substring(0, 10);
        matchesDate = normalizedBookingDate === normalizedFilterDate;
      } else {
        matchesDate = false;
      }
    }

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
            {filteredBookings.length > 0 ? filteredBookings.map((booking, index) => (
              <tr key={booking.id || booking.pk || index}>
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
                <label style={{ fontSize: '12px', fontWeight: 'bold', color: '#6B7A90', textTransform: 'uppercase', display: 'block', marginBottom: '6px' }}>
                  {isClientPortal ? 'Booking For' : 'Select Client *'}
                </label>
                {isClientPortal ? (
                  <input
                    type="text"
                    readOnly
                    disabled
                    value={myClient ? `${myClient.full_name} (${myClient.email})` : 'Loading your account...'}
                    style={{ width: '100%', background: '#E3E8F0', border: 'none', borderRadius: '12px', padding: '10px', fontSize: '14px', color: '#6B7A90', outline: 'none', cursor: 'not-allowed' }}
                  />
                ) : (
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
                )}
              </div>

              <div>
                <label style={{ fontSize: '12px', fontWeight: 'bold', color: '#6B7A90', textTransform: 'uppercase', display: 'block', marginBottom: '6px' }}>Service *</label>
                <select
                  required
                  value={formData.service}
                  onChange={(e) => setFormData({...formData, service: e.target.value})}
                  style={{ width: '100%', background: '#EEF2F9', border: 'none', borderRadius: '12px', padding: '10px', fontSize: '14px', color: '#1E2A3A', outline: 'none' }}
                >
                  <option value="">-- Select a Service --</option>
                  {services.map(s => (
                    <option key={s.id} value={s.id}>{s.name} (${s.hourly_rate}/hr)</option>
                  ))}
                </select>
                {(() => {
                  const selected = services.find((s) => String(s.id) === String(formData.service));
                  return selected?.description ? (
                    <p style={{ fontSize: '11px', color: '#6B7A90', margin: '6px 0 0' }}>{selected.description}</p>
                  ) : null;
                })()}
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

              {/* Read-only preview — the backend always recalculates and validates the real total on save. */}
              {(() => {
                const preview = estimatePrice(formData.service, formData.start_time, formData.end_time);
                return preview ? (
                  <div style={{ background: '#E3E8F0', borderRadius: '12px', padding: '12px 14px', fontSize: '13px', color: '#1E2A3A' }}>
                    <strong>Duration:</strong> {preview.durationHours.toFixed(2)} hrs &nbsp;·&nbsp;
                    <strong>Rate:</strong> ${preview.rate.toFixed(2)}/hr &nbsp;·&nbsp;
                    <strong>Estimated Total:</strong> ${preview.total.toFixed(2)}
                  </div>
                ) : null;
              })()}

              <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', marginTop: '12px' }}>
                <button
                  type="button"
                  onClick={() => { setShowModal(false); setBookingViaSlotLink(false); }}
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
                <button
                  type="button"
                  onClick={() => {
                    const params = formData.booking_date ? `?date=${formData.booking_date}` : '';
                    navigate(`${slotsPagePath}${params}`);
                  }}
                  className="neu-btn"
                  style={{ background: '#EEF2F9', color: '#3E7BFA', border: 'none', cursor: 'pointer', fontWeight: 600 }}
                >
                  Available Slots
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
                  <button onClick={() => { setIsEditing(true); setServiceTouched(false); }} className="neu-btn neu-btn-primary" style={{ border: 'none', cursor: 'pointer' }}>Edit / Change Status</button>
                  <button
                    onClick={() => handleDeleteBooking(selectedBooking)}
                    style={{ background: '#FDE8E8', color: '#9B1C1C', border: 'none', padding: '8px 16px', borderRadius: '8px', cursor: 'pointer', fontWeight: '600' }}
                  >
                    Delete
                  </button>
                  <button onClick={() => { setSelectedBooking(null); setShowEditSlots(false); }} className="neu-btn" style={{ background: '#EEF2F9', border: 'none', cursor: 'pointer' }}>Close</button>
                </div>
              </div>
            ) : (
              // EDIT / STATUS CHANGE FORM MODE
              <form onSubmit={handleUpdateBooking} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div>
                  <label style={{ fontSize: '12px', fontWeight: 'bold', color: '#6B7A90', display: 'block', marginBottom: '4px' }}>Service</label>
                  <select
                    value={selectedBooking.service || ''}
                    onChange={(e) => { setSelectedBooking({...selectedBooking, service: e.target.value}); setServiceTouched(true); }}
                    style={{ width: '100%', background: '#EEF2F9', border: 'none', borderRadius: '8px', padding: '8px', outline: 'none' }}
                  >
                    <option value="">-- Select a Service --</option>
                    {services.map(s => (
                      <option key={s.id} value={s.id}>{s.name} (${s.hourly_rate}/hr)</option>
                    ))}
                  </select>
                  {(() => {
                    const selected = services.find((s) => String(s.id) === String(selectedBooking.service));
                    if (selected?.description) {
                      return <p style={{ fontSize: '11px', color: '#6B7A90', margin: '4px 0 0' }}>{selected.description}</p>;
                    }
                    if (!serviceTouched && selectedBooking.service_name) {
                      return <p style={{ fontSize: '11px', color: '#6B7A90', margin: '4px 0 0' }}>{selectedBooking.service_name}</p>;
                    }
                    return null;
                  })()}
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
                    <div style={{ padding: '8px 0' }}>
                      <PaymentStatusBadge status={selectedBooking.payment_status} />
                    </div>
                    <p style={{ fontSize: '11px', color: '#6B7A90', margin: '4px 0 0' }}>Manage via the Payments page.</p>
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

                <div>
                  <button
                    type="button"
                    onClick={() => {
                      if (!selectedBooking.booking_date) {
                        toast.error('Pick a date first to see available slots.');
                        return;
                      }
                      setShowEditSlots((v) => !v);
                    }}
                    style={{ background: 'transparent', border: 'none', color: '#3E7BFA', fontSize: '13px', fontWeight: 600, cursor: 'pointer', padding: 0 }}
                  >
                    {showEditSlots ? 'Hide Available Slots' : 'View Available Slots (for rescheduling)'}
                  </button>
                  {showEditSlots && (
                    <div style={{ marginTop: '8px' }}>
                      <AvailableSlotsPanel
                        date={selectedBooking.booking_date}
                        isStaff={!isClientPortal}
                        onSelectSlot={(start, end) => {
                          setSelectedBooking((prev) => ({ ...prev, start_time: start.substring(0, 5), end_time: end.substring(0, 5) }));
                          setShowEditSlots(false);
                        }}
                      />
                    </div>
                  )}
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

                {/* Price is backend-calculated and read-only — never trust a manually entered value. */}
                <div style={{ background: '#E3E8F0', borderRadius: '8px', padding: '10px 12px', fontSize: '13px', color: '#1E2A3A' }}>
                  {(() => {
                    const preview = estimatePrice(
                      selectedBooking.service,
                      formatTimeForInput(selectedBooking.start_time),
                      formatTimeForInput(selectedBooking.end_time)
                    );
                    if (serviceTouched && preview) {
                      return (
                        <>
                          <strong>Duration:</strong> {preview.durationHours.toFixed(2)} hrs &nbsp;·&nbsp;
                          <strong>Rate:</strong> ${preview.rate.toFixed(2)}/hr &nbsp;·&nbsp;
                          <strong>New Estimated Total:</strong> ${preview.total.toFixed(2)}
                        </>
                      );
                    }
                    return (
                      <>
                        <strong>Current Price:</strong> ${selectedBooking.price}
                        {selectedBooking.rate_snapshot && ` (locked at $${selectedBooking.rate_snapshot}/hr)`}
                      </>
                    );
                  })()}
                </div>

                <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '12px' }}>
                  <button type="button" onClick={() => { setIsEditing(false); setServiceTouched(false); setShowEditSlots(false); }} className="neu-btn" style={{ background: '#EEF2F9', border: 'none', cursor: 'pointer' }}>Cancel</button>
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