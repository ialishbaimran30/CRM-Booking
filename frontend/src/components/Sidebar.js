import React from 'react';
import { Link, useLocation } from 'react-router-dom';

export default function Sidebar() {
  const location = useLocation();
  const isActive = (path) => location.pathname.startsWith(path);

  return (
    <div className="w-64 bg-[#EEF2F9] border-r border-[#d0d9e8]/50 min-h-screen flex flex-col justify-between p-6">
      <div>
        <div className="mb-8">
          <h1 className="text-xl font-bold text-[#3E7BFA] tracking-tight">CRM & Booking</h1>
          <p className="text-xs text-[#6B7A90] font-medium mt-0.5">Management Portal</p>
        </div>

        <nav className="flex flex-col gap-2">
          <Link
            to="/dashboard"
            className={`flex items-center gap-3.5 px-4 py-3 rounded-xl text-sm font-semibold transition-all duration-200 ${
              isActive('/dashboard')
                ? 'bg-[#3E7BFA] text-white shadow-[4px_4px_10px_rgba(62,123,250,0.3)]'
                : 'text-[#6B7A90] hover:text-[#1E2A3A] hover:bg-[#F4F7FC]'
            }`}
          >
            <span>📊</span> Dashboard
          </Link>
          <Link
            to="/clients"
            className={`flex items-center gap-3.5 px-4 py-3 rounded-xl text-sm font-semibold transition-all duration-200 ${
              isActive('/clients')
                ? 'bg-[#3E7BFA] text-white shadow-[4px_4px_10px_rgba(62,123,250,0.3)]'
                : 'text-[#6B7A90] hover:text-[#1E2A3A] hover:bg-[#F4F7FC]'
            }`}
          >
            <span>👥</span> Clients Management
          </Link>
          <Link
            to="/bookings"
            className={`flex items-center gap-3.5 px-4 py-3 rounded-xl text-sm font-semibold transition-all duration-200 ${
              isActive('/bookings')
                ? 'bg-[#3E7BFA] text-white shadow-[4px_4px_10px_rgba(62,123,250,0.3)]'
                : 'text-[#6B7A90] hover:text-[#1E2A3A] hover:bg-[#F4F7FC]'
            }`}
          >
            <span>📅</span> Bookings
          </Link>
          <Link
            to="/payments"
            className={`flex items-center gap-3.5 px-4 py-3 rounded-xl text-sm font-semibold transition-all duration-200 ${
              isActive('/payments')
                ? 'bg-[#3E7BFA] text-white shadow-[4px_4px_10px_rgba(62,123,250,0.3)]'
                : 'text-[#6B7A90] hover:text-[#1E2A3A] hover:bg-[#F4F7FC]'
            }`}
          >
            <span>💳</span> Payments
          </Link>
          <Link
            to="/reports"
            className={`flex items-center gap-3.5 px-4 py-3 rounded-xl text-sm font-semibold transition-all duration-200 ${
              isActive('/reports')
                ? 'bg-[#3E7BFA] text-white shadow-[4px_4px_10px_rgba(62,123,250,0.3)]'
                : 'text-[#6B7A90] hover:text-[#1E2A3A] hover:bg-[#F4F7FC]'
            }`}
          >
            <span>📊</span> Reports
          </Link>
        </nav>
      </div>
    </div>
  );
}