import api from './axiosInstance';

// Reuses the existing notifications app endpoints — this is the same
// recipient-scoped list used for the bell dropdown AND (for Admin, who is
// always a recipient of every booking event) the Notification History page.
export const notificationService = {
  getNotifications: async () => {
    const response = await api.get('/notifications/notifications/');
    return response.data;
  },
  markAsRead: async (id) => {
    const response = await api.post(`/notifications/notifications/${id}/mark_as_read/`);
    return response.data;
  },
};
