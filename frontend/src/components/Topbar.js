import React, { useState, useRef, useEffect } from 'react';

export default function Topbar({ user, onLogout, onEditProfile }) {
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div className="h-16 bg-white border-b border-gray-100 px-8 flex justify-between items-center sticky top-0 z-30 shadow-sm">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-gray-700">Welcome back, <span className="text-blue-600">{user?.full_name || 'User'}</span> 👋</span>
      </div>

      {/* User Profile Dropdown Container */}
      <div className="relative" ref={dropdownRef}>
        <button 
          onClick={() => setDropdownOpen(!dropdownOpen)}
          className="flex items-center gap-3 focus:outline-none group"
        >
          <img 
            src={user?.profile_picture_url || "https://via.placeholder.com/40"} 
            alt="Profile" 
            className="w-10 h-10 rounded-full object-cover border-2 border-blue-100 group-hover:border-blue-500 transition"
          />
        </button>

        {/* Dropdown Menu */}
        {dropdownOpen && (
          <div className="absolute right-0 mt-3 w-72 bg-white rounded-2xl shadow-xl border border-gray-100 py-3 z-50 animate-in fade-in zoom-in-95 duration-150">
            {/* User Info Header */}
            <div className="px-5 pb-3 border-b border-gray-100 text-center">
              <img 
                src={user?.profile_picture_url || "https://via.placeholder.com/60"} 
                alt="Profile" 
                className="w-14 h-14 rounded-full object-cover mx-auto mb-2 border border-blue-200"
              />
              <p className="font-bold text-gray-900">{user?.full_name || 'Alishba Imran'}</p>
              <p className="text-xs text-gray-400 truncate mt-0.5">{user?.email}</p>
            </div>

            {/* Menu Options */}
            <div className="py-2 px-2 text-sm">
              <button 
                onClick={() => { setDropdownOpen(false); onEditProfile(); }}
                className="w-full text-left px-3 py-2 text-gray-700 hover:bg-blue-50 hover:text-blue-600 rounded-xl font-medium transition flex items-center gap-2"
              >
                <span>⚙️</span> Edit Profile
              </button>
            </div>

            <div className="border-t border-gray-100 pt-2 px-2">
              <button 
                onClick={() => { setDropdownOpen(false); onLogout(); }}
                className="w-full text-left px-3 py-2 text-red-600 hover:bg-red-50 rounded-xl font-medium transition flex items-center gap-2"
              >
                <span>🚪</span> Sign Out
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}