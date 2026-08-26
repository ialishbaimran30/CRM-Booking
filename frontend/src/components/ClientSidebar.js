import React from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { logout as logoutRequest } from '../api/authService';

export default function ClientSidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const isActive = (path) => location.pathname.startsWith(path);

  const handleLogout = () => {
    // logoutRequest() blacklists the refresh token server-side (M-1) and
    // clears the auth keys itself; clear anything else (e.g.
    // cleared_notification_ids) separately rather than a blanket
    // localStorage.clear(), which would race with it.
    logoutRequest();
    localStorage.removeItem('cleared_notification_ids');
    navigate('/login');
  };

  return (
    <div className="w-64 bg-[#EEF2F9] border-r border-[#d0d9e8]/50 min-h-screen flex flex-col justify-between p-6">
      <div>
        <div className="mb-8">
          <h1 className="text-xl font-bold text-[#3E7BFA] tracking-tight">Client Portal</h1>
          <p className="text-xs text-[#6B7A90] font-medium mt-0.5">My Account</p>
        </div>

        <nav className="flex flex-col gap-2">
          <Link
            to="/client-portal/bookings"
            className={`flex items-center gap-3.5 px-4 py-3 rounded-xl text-sm font-semibold transition-all duration-200 ${
              isActive('/client-portal/bookings')
                ? 'bg-[#3E7BFA] text-white shadow-[4px_4px_10px_rgba(62,123,250,0.3)]'
                : 'text-[#6B7A90] hover:text-[#1E2A3A] hover:bg-[#F4F7FC]'
            }`}
          >
            <span>📅</span> My Bookings
          </Link>
          <Link
            to="/client-portal/available-slots"
            className={`flex items-center gap-3.5 px-4 py-3 rounded-xl text-sm font-semibold transition-all duration-200 ${
              isActive('/client-portal/available-slots')
                ? 'bg-[#3E7BFA] text-white shadow-[4px_4px_10px_rgba(62,123,250,0.3)]'
                : 'text-[#6B7A90] hover:text-[#1E2A3A] hover:bg-[#F4F7FC]'
            }`}
          >
            <span>🗓️</span> Available Slots
          </Link>
          <Link
            to="/client-portal/waitlist"
            className={`flex items-center gap-3.5 px-4 py-3 rounded-xl text-sm font-semibold transition-all duration-200 ${
              isActive('/client-portal/waitlist')
                ? 'bg-[#3E7BFA] text-white shadow-[4px_4px_10px_rgba(62,123,250,0.3)]'
                : 'text-[#6B7A90] hover:text-[#1E2A3A] hover:bg-[#F4F7FC]'
            }`}
          >
            <span>⏳</span> Waitlist
          </Link>
        </nav>
      </div>

      {/* <div>
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-3.5 px-4 py-3 rounded-xl text-sm font-semibold text-red-600 hover:bg-red-50 transition-all duration-200"
        >
          <span>🚪</span> Logout
        </button>
      </div> */}
    </div>
  );
}