import api from './axiosInstance';

export const bookingService = {
  // Get all bookings
  getBookings: async (params = {}) => {
    const response = await api.get('/bookings/', { params });
    return response.data;
  },

  // Get single booking details
  getBookingDetail: async (id) => {
    const response = await api.get(`/bookings/${id}/`);
    return response.data;
  },

  // Create new booking
  createBooking: async (bookingData) => {
    const response = await api.post('/bookings/', bookingData);
    return response.data;
  },

  // Get available slots for scheduling
  getAvailableSlots: async (date) => {
    const response = await api.get('/bookings/available-slots/', { params: { date } });
    return response.data;
  },

  // Get the Admin-defined catalog of bookable services (id, name, hourly_rate)
  getServices: async () => {
    const response = await api.get('/services/');
    return response.data;
  },

  // Update booking status or details
  updateBooking: async (id, bookingData) => {
    const response = await api.patch(`/bookings/${id}/`, bookingData);
    return response.data;
  },

  // Cancel booking
  cancelBooking: async (id) => {
    const response = await api.post(`/bookings/${id}/cancel/`);
    return response.data;
  },
  // bookingService.js ke andar yeh function hona chahiye:
  deleteBooking: async (id) => {
    const response = await api.delete(`/bookings/${id}/`); // ya jo bhi aapka Axios instance hai
    return response.data;
  },
};