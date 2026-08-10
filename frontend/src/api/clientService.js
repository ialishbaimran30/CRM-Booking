import api from './axiosInstance';
export const clientService = {
  getClients: async (params = {}) => {
    const response = await api.get('/clients/', { params });
    return response.data;
  },
  getClientDetail: async (id) => {
    const response = await api.get(`/clients/${id}/`);
    return response.data;
  },
  getMyClient: async () => {
    const response = await api.get('/clients/me/');
    return response.data;
  },
  createClient: async (clientData) => {
    const response = await api.post('/clients/', clientData);
    return response.data;
  },
  updateClient: async (id, clientData) => {
    const response = await api.put(`/clients/${id}/`, clientData);
    return response.data;
  },
  deleteClient: async (id) => {
    const response = await api.delete(`/clients/${id}/`);
    return response.data;
  },
};