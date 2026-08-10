// The backend is the single source of truth for role: `user.role` is
// 'Admin', 'Booking Manager', or null (no Staff Role — a Client). The
// frontend never lets a user pick their own role; it only ever reflects
// whatever the backend returned at login / on refresh.

export function getCurrentUser() {
  try {
    return JSON.parse(localStorage.getItem('user') || 'null');
  } catch (e) {
    return null;
  }
}

export function isStaffUser(user) {
  return !!user?.role;
}
