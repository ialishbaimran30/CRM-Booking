import React, { useState, useEffect, useCallback } from 'react';
import api from './api/axiosInstance';
import { isStaffUser } from './utils/session';
import { notificationService } from './api/notificationService';
import useNotificationSocket from './hooks/useNotificationSocket';
import AuthScreen from './components/AuthScreen';
import Sidebar from './components/Sidebar';
import ClientSidebar from './components/ClientSidebar'; // New dedicated client sidebar
import Topbar from './components/Topbar';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import ClientListPage from './pages/ClientListPage';
import ClientDetailPage from './pages/ClientDetailPage';
import DashboardPage from './pages/DashboardPage';
import BookingListPage from './pages/BookingListPage';
import AvailableSlotsPage from './pages/AvailableSlotsPage';
import WaitlistPage from './pages/WaitlistPage';
import PaymentsView from './pages/PaymentsView';
import ReportsView from './pages/ReportsView';
import TeamManagement from './pages/TeamManagement';
import NotificationHistoryPage from './pages/NotificationHistoryPage';
import toast, { Toaster } from 'react-hot-toast';
import './App.css';

export default function App() {
  const [user, setUser] = useState(null);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editName, setEditName] = useState('');

  useEffect(() => {
    const savedUser = localStorage.getItem('user');
    if (savedUser) {
      try {
        const parsed = JSON.parse(savedUser);
        setUser(parsed);
        setEditName(parsed.full_name || '');
      } catch (e) {
        console.error("Failed to parse user", e);
      }
    }
  }, []);

  // The backend is the single source of truth for role — a localStorage snapshot
  // taken at login time can go stale (e.g. after a role transfer, or if it predates
  // the role ever being included in the login response). Re-fetch it on load and
  // right after authentication, and refresh the cached user object with the result.
  useEffect(() => {
    if (!user?.id) return;
    let cancelled = false;

    api.get('/accounts/team-roles/me/')
      .then(({ data }) => {
        if (cancelled || !data) return;
        setUser((prev) => {
          if (!prev) return prev;
          const refreshed = { ...prev, ...data };
          localStorage.setItem('user', JSON.stringify(refreshed));
          return refreshed;
        });
      })
      .catch((err) => {
        console.error('Failed to refresh current user role:', err);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  // Notification History / bell: fetch the user's existing notifications once
  // logged in, then keep the list live via WebSocket — the same
  // /api/notifications/notifications/ endpoint backs both the bell dropdown
  // and (for Admin) the Notification History page.
  const [notifications, setNotifications] = useState([]);
  const unreadCount = notifications.filter((n) => !n.is_read).length;

  useEffect(() => {
    if (!user?.id) return;
    notificationService.getNotifications()
      .then((data) => setNotifications(Array.isArray(data) ? data : (data.results || [])))
      .catch((err) => console.error('Failed to load notifications:', err));
  }, [user?.id]);

  const handleIncomingNotification = useCallback((notification) => {
    // One WebSocket message = one already-created Notification row — just
    // add it to local state and surface exactly one toast, never re-created.
    setNotifications((prev) => {
      if (prev.some((n) => n.id === notification.id)) return prev;
      return [notification, ...prev];
    });
    toast(notification.title, { icon: '🔔' });
  }, []);

  useNotificationSocket(!!user, handleIncomingNotification);

  const handleMarkNotificationRead = async (id) => {
    try {
      await notificationService.markAsRead(id);
      setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
    } catch (err) {
      console.error('Failed to mark notification as read:', err);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
    setUser(null);
  };

  const handleUpdateProfile = (e) => {
    e.preventDefault();
    const updatedUser = { ...user, full_name: editName };
    setUser(updatedUser);
    localStorage.setItem('user', JSON.stringify(updatedUser));
    setShowEditModal(false);
  };

  // Backend-driven role determination (single source of truth): a user with no
  // Staff Role (`role` is null) is a Client — the app never lets anyone self-select this.
  const isClientUser = !!user && !isStaffUser(user);
  // Only the Admin role gets Dashboard, Reports, and Team Management — Booking Manager lands on Clients.
  const isAdminUser = !isClientUser && user?.role === 'Admin';

  return (
    <Router>
      <Toaster position="top-right" toastOptions={{ duration: 4000 }} />
      {user ? (
        <div className="flex h-screen overflow-hidden bg-[#EEF2F9]">
          {/* Dynamically render separate sidebars without changing staff layout */}
          {isClientUser ? <ClientSidebar /> : <Sidebar isAdmin={isAdminUser} />}
          
          <div className="flex-1 flex flex-col overflow-y-auto">
            <Topbar
              user={user}
              onLogout={handleLogout}
              onEditProfile={() => setShowEditModal(true)}
              notifications={notifications}
              unreadCount={unreadCount}
              onMarkNotificationRead={handleMarkNotificationRead}
            />
            <div className="flex-1 overflow-y-auto p-8">
              <Routes>
                {isClientUser ? (
                  /* CLIENT PORTAL ROUTES: Strict restriction to My Bookings (+ Available Slots / Waitlist) */
                  <>
                    <Route path="/client-portal/bookings" element={<BookingListPage />} />
                    <Route path="/client-portal/available-slots" element={<AvailableSlotsPage />} />
                    <Route path="/client-portal/waitlist" element={<WaitlistPage />} />
                    <Route path="*" element={<Navigate to="/client-portal/bookings" replace />} />
                  </>
                ) : (
                  /* STAFF CRM ROUTES: Admin gets everything; Booking Manager gets everything
                     except Dashboard, Reports, and Team Management (redirected to Clients). */
                  <>
                    {isAdminUser && <Route path="/dashboard" element={<DashboardPage />} />}
                    <Route path="/clients" element={<ClientListPage />} />
                    <Route path="/bookings" element={<BookingListPage />} />
                    <Route path="/bookings/available-slots" element={<AvailableSlotsPage />} />
                    <Route path="/waitlist" element={<WaitlistPage />} />
                    <Route path="/payments" element={<PaymentsView isAdmin={isAdminUser} />} />
                    {isAdminUser && <Route path="/reports" element={<ReportsView />} />}
                    {isAdminUser && <Route path="/team-management" element={<TeamManagement />} />}
                    {isAdminUser && <Route path="/notification-history" element={<NotificationHistoryPage />} />}
                    <Route path="/clients/:id" element={<ClientDetailPage />} />
                    <Route path="*" element={<Navigate to={isAdminUser ? "/dashboard" : "/clients"} replace />} />
                  </>
                )}
              </Routes>
            </div>
          </div>

          {/* Edit Profile Modal */}
          {showEditModal && (
            <div className="fixed inset-0 bg-[#1E2A3A]/40 backdrop-blur-sm flex justify-center items-center z-50 p-4">
              <div className="bg-[#F4F7FC] p-6 rounded-2xl shadow-[12px_12px_24px_#d0d9e8,-12px_-12px_24px_#ffffff] w-full max-w-md border border-[#d0d9e8]/50">
                <h2 className="text-xl font-bold text-[#1E2A3A] mb-4">Edit Profile</h2>
                <form onSubmit={handleUpdateProfile} className="space-y-4">
                  <div>
                    <label className="block text-xs font-semibold text-[#6B7A90] uppercase tracking-wider mb-1">Full Name</label>
                    <input 
                      type="text" 
                      value={editName} 
                      onChange={(e) => setEditName(e.target.value)}
                      className="w-full bg-[#EEF2F9] border-none p-2.5 rounded-xl text-sm text-[#1E2A3A] focus:ring-2 focus:ring-[#3E7BFA] outline-none"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-[#6B7A90] uppercase tracking-wider mb-1">Email (Read-only)</label>
                    <input 
                      type="email" 
                      value={user.email} 
                      disabled
                      className="w-full bg-[#EEF2F9]/50 border-none p-2.5 rounded-xl text-sm text-[#6B7A90] outline-none cursor-not-allowed"
                    />
                  </div>
                  <div className="flex justify-end gap-3 pt-2">
                    <button 
                      type="button" 
                      onClick={() => setShowEditModal(false)} 
                      className="px-4 py-2 bg-[#EEF2F9] text-[#6B7A90] hover:text-[#1E2A3A] rounded-xl text-sm font-medium shadow-[3px_3px_6px_#d0d9e8,-3px_-3px_6px_#ffffff] transition"
                    >
                      Cancel
                    </button>
                    <button 
                      type="submit" 
                      className="px-4 py-2 bg-[#3E7BFA] text-white hover:bg-[#2E63D6] rounded-xl text-sm font-medium transition shadow-[4px_4px_10px_rgba(62,123,250,0.3)]"
                    >
                      Save Changes
                    </button>
                  </div>
                </form>
              </div>
            </div>
          )}
        </div>
      ) : (
        <AuthScreen
          onLoginSuccess={(userData) => {
            setUser(userData);
            setEditName(userData.full_name || '');
          }}
        />
      )}
    </Router>
  );
}