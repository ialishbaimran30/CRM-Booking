import React, { useState, useEffect } from 'react';
import GoogleAuthButton from './components/GoogleAuthButton';
import Sidebar from './components/Sidebar';
import Topbar from './components/Topbar';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import ClientListPage from './pages/ClientListPage';
import ClientDetailPage from './pages/ClientDetailPage';
import DashboardPage from './pages/DashboardPage';
import BookingListPage from './pages/BookingListPage';
import PaymentsView from './pages/PaymentsView';
import ReportsView from './pages/ReportsView';
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

  return (
    <Router>
      {user ? (
        <div className="flex min-h-screen bg-[#EEF2F9]">
          <Sidebar />
          <div className="flex-1 flex flex-col overflow-y-auto">
            <Topbar 
              user={user} 
              onLogout={handleLogout} 
              onEditProfile={() => setShowEditModal(true)} 
            />
            <div className="flex-1 p-8">
              <Routes>
                <Route path="/dashboard" element={<DashboardPage />} />
                <Route path="/clients" element={<ClientListPage />} />
                <Route path="/bookings" element={<BookingListPage />} />
                <Route path="/payments" element={<PaymentsView />} />
                <Route path="/reports" element={<ReportsView />} />
                <Route path="/clients/:id" element={<ClientDetailPage />} />
                <Route path="*" element={<Navigate to="/dashboard" replace />} />
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
        <div className="min-h-screen bg-[#EEF2F9] flex items-center justify-center p-4">
          <div className="bg-[#F4F7FC] p-8 rounded-2xl shadow-[12px_12px_24px_#d0d9e8,-12px_-12px_24px_#ffffff] w-full max-w-md text-center border border-[#d0d9e8]/50">
            <h1 className="text-2xl font-bold mb-2 text-[#1E2A3A]">CRM & Booking Portal</h1>
            <p className="text-[#6B7A90] text-sm mb-6">Sign in with your authorized Google account</p>
            <GoogleAuthButton onLoginSuccess={(userData) => {
              setUser(userData);
              setEditName(userData.full_name || '');
            }} />
          </div>
        </div>
      )}
    </Router>
  );
}