import api from './axiosInstance';

// M-1: tells the server to blacklist the refresh token, not just clear
// local storage — a "logged out" session should not still be a valid,
// replayable credential for up to 7 days. Never blocks sign-out on
// failure (network error, already-expired token, etc.) since the local
// clear below is what actually ends the session from the user's side.
export async function logout() {
  const refresh = localStorage.getItem('refresh_token');
  if (refresh) {
    try {
      await api.post('/accounts/logout/', { refresh });
    } catch (err) {
      console.error('Server-side logout failed (session cleared locally regardless):', err);
    }
  }
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('user');
}
