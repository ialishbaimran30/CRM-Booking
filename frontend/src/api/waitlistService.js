import api from './axiosInstance';

export const waitlistService = {
  getWaitlist: async (params = {}) => {
    const response = await api.get('/waitlist/', { params });
    return response.data;
  },
  joinWaitlist: async (data) => {
    const response = await api.post('/waitlist/', data);
    return response.data;
  },
  leaveWaitlist: async (id) => {
    const response = await api.delete(`/waitlist/${id}/`);
    return response.data;
  },
};
