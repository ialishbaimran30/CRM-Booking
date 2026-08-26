import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://127.0.0.1:8000/api';

const api = axios.create({
  baseURL: API_BASE_URL,
});

// Automatically attach JWT token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
}, (error) => {
  return Promise.reject(error);
});

// M-1: refresh-on-401. ACCESS_TOKEN_LIFETIME is short (15 minutes) so a
// session staying open depends on this — without it, every user would be
// silently kicked to a 401 every 15 minutes instead of staying signed in.
// Deduplicated so concurrent 401s trigger one refresh call, not several.
let refreshPromise = null;

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    const isRefreshCall = originalRequest?.url?.includes('/token/refresh/');

    if (error.response?.status !== 401 || !originalRequest || originalRequest._retry || isRefreshCall) {
      return Promise.reject(error);
    }

    const refreshToken = localStorage.getItem('refresh_token');
    if (!refreshToken) {
      return Promise.reject(error);
    }

    originalRequest._retry = true;
    try {
      if (!refreshPromise) {
        refreshPromise = axios
          .post(`${API_BASE_URL}/accounts/token/refresh/`, { refresh: refreshToken })
          .finally(() => {
            refreshPromise = null;
          });
      }
      const { data } = await refreshPromise;
      localStorage.setItem('access_token', data.access);
      // SIMPLE_JWT.ROTATE_REFRESH_TOKENS is on — the old refresh token is
      // blacklisted server-side the moment this response is returned, so
      // the new one must replace it or the next refresh will fail.
      if (data.refresh) {
        localStorage.setItem('refresh_token', data.refresh);
      }
      originalRequest.headers.Authorization = `Bearer ${data.access}`;
      return api(originalRequest);
    } catch (refreshError) {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      localStorage.removeItem('user');
      window.location.href = '/';
      return Promise.reject(refreshError);
    }
  }
);

export default api;