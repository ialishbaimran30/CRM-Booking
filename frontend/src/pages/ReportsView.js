import React, { useState, useEffect, useCallback } from 'react';
import { NeumorphicCard } from '../components/common/NeumorphicCard';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';
import toast from 'react-hot-toast';

export default function ReportsView() {
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState('monthly'); // daily, weekly, monthly
  
  const [reportData, setReportData] = useState({
    bookings_summary: { total: 0, pending: 0, confirmed: 0, completed: 0, cancelled: 0 },
    revenue_summary: { total_revenue: 0, pending_amount: 0, refunded_amount: 0 },
    top_services: [],
    new_clients_count: 0,
    cancellation_rate: 0,
    chart_data: []
  });

  const fetchReports = useCallback(async (showLoader = false) => {
    try {
      if (showLoader) setLoading(true);
      const token = localStorage.getItem('access_token');
      const headers = { 'Authorization': `Bearer ${token}` };

      const res = await fetch(`/api/reports/periodic/?period=${period}`, { headers });
      
      if (res.ok) {
        const data = await res.json();
        setReportData({
          bookings_summary: data.bookings_summary || { total: 0, pending: 0, confirmed: 0, completed: 0, cancelled: 0 },
          revenue_summary: data.revenue_summary || { total_revenue: 0, pending_amount: 0, refunded_amount: 0 },
          top_services: data.top_services || [],
          new_clients_count: data.new_clients_count ?? 0,
          cancellation_rate: data.cancellation_rate ?? 0,
          chart_data: data.chart_data || (Array.isArray(data) ? data : [])
        });
      } else {
        toast.error("Failed to load reports from server.");
      }
    } catch (err) {
      console.error("Error fetching reports:", err);
      toast.error("An error occurred while fetching reports.");
    } finally {
      if (showLoader) setLoading(false);
    }
  }, [period]);

  useEffect(() => {
    fetchReports(true);
  }, [period, fetchReports]);

  // Real-time synchronization listener for cross-module changes (Bookings, Payments, Clients)
  useEffect(() => {
    const handleStorageSync = (e) => {
      if (
        e.key === 'payment_sync_timestamp' || 
        e.key === 'booking_sync_timestamp' || 
        e.key === 'client_sync_timestamp' ||
        !e.key
      ) {
        fetchReports(false);
      }
    };

    window.addEventListener('storage', handleStorageSync);
    
    // Fallback polling for same-tab cross-module state updates
    const interval = setInterval(() => {
      const syncStamp = localStorage.getItem('payment_sync_timestamp');
      if (syncStamp && syncStamp !== window._lastReportSyncStamp) {
        window._lastReportSyncStamp = syncStamp;
        fetchReports(false);
      }
    }, 1000);

    return () => {
      window.removeEventListener('storage', handleStorageSync);
      clearInterval(interval);
    };
  }, [fetchReports]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-[#1E2A3A]">Business Reports</h2>
          <p className="text-sm text-[#6B7A90]">Analyze revenue trends, booking volumes, and business health indicators.</p>
        </div>

        {/* Period Selector Tabs */}
        <div className="flex items-center bg-[#EEF2F9] p-1.5 rounded-xl shadow-inner">
          <button 
            onClick={() => setPeriod('daily')}
            className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${period === 'daily' ? 'bg-[#3E7BFA] text-white shadow' : 'text-[#6B7A90] hover:text-[#1E2A3A]'}`}
          >
            Daily
          </button>
          <button 
            onClick={() => setPeriod('weekly')}
            className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${period === 'weekly' ? 'bg-[#3E7BFA] text-white shadow' : 'text-[#6B7A90] hover:text-[#1E2A3A]'}`}
          >
            Weekly
          </button>
          <button 
            onClick={() => setPeriod('monthly')}
            className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${period === 'monthly' ? 'bg-[#3E7BFA] text-white shadow' : 'text-[#6B7A90] hover:text-[#1E2A3A]'}`}
          >
            Monthly
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-16 text-[#6B7A90]">Loading live report analytics...</div>
      ) : (
        <>
          {/* Section 1: Bookings Summary */}
          <div>
            <h3 className="text-sm font-bold text-[#6B7A90] uppercase tracking-wider mb-3">Bookings Summary</h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
              <NeumorphicCard className="p-4">
                <p className="text-xs font-semibold text-[#6B7A90]">Total Bookings</p>
                <h4 className="text-2xl font-extrabold text-[#1E2A3A] mt-1">{reportData.bookings_summary.total}</h4>
              </NeumorphicCard>
              <NeumorphicCard className="p-4">
                <p className="text-xs font-semibold text-[#6B7A90]">Pending</p>
                <h4 className="text-2xl font-extrabold text-[#E0A800] mt-1">{reportData.bookings_summary.pending}</h4>
              </NeumorphicCard>
              <NeumorphicCard className="p-4">
                <p className="text-xs font-semibold text-[#6B7A90]">Confirmed</p>
                <h4 className="text-2xl font-extrabold text-[#3E7BFA] mt-1">{reportData.bookings_summary.confirmed}</h4>
              </NeumorphicCard>
              <NeumorphicCard className="p-4">
                <p className="text-xs font-semibold text-[#6B7A90]">Completed</p>
                <h4 className="text-2xl font-extrabold text-[#3FBF8F] mt-1">{reportData.bookings_summary.completed}</h4>
              </NeumorphicCard>
              <NeumorphicCard className="p-4 col-span-2 sm:col-span-1">
                <p className="text-xs font-semibold text-[#6B7A90]">Cancelled</p>
                <h4 className="text-2xl font-extrabold text-[#9B1C1C] mt-1">{reportData.bookings_summary.cancelled}</h4>
              </NeumorphicCard>
            </div>
          </div>

          {/* Section 2: Revenue Summary, New Clients & Cancellation Rate */}
          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
            <NeumorphicCard className="p-4 md:col-span-3 grid grid-cols-3 gap-2">
              <div className="col-span-3 mb-1">
                <h3 className="text-sm font-bold text-[#6B7A90] uppercase tracking-wider">Revenue Summary</h3>
              </div>
              <div>
                <p className="text-xs text-[#6B7A90]">Collected</p>
                <h4 className="text-xl font-extrabold text-[#3FBF8F] mt-0.5">${reportData.revenue_summary.total_revenue}</h4>
              </div>
              <div>
                <p className="text-xs text-[#6B7A90]">Pending Amt</p>
                <h4 className="text-xl font-extrabold text-[#E0A800] mt-0.5">${reportData.revenue_summary.pending_amount}</h4>
              </div>
              <div>
                <p className="text-xs text-[#6B7A90]">Refunded</p>
                <h4 className="text-xl font-extrabold text-[#9B1C1C] mt-0.5">${reportData.revenue_summary.refunded_amount}</h4>
              </div>
            </NeumorphicCard>

            <NeumorphicCard className="p-4 flex flex-col justify-between">
              <h3 className="text-xs font-bold text-[#6B7A90] uppercase tracking-wider">New Clients</h3>
              <div>
                <h4 className="text-2xl font-extrabold text-[#3E7BFA]">{reportData.new_clients_count}</h4>
                <p className="text-xs text-[#6B7A90] mt-0.5">Added in this period</p>
              </div>
            </NeumorphicCard>

            <NeumorphicCard className="p-4 flex flex-col justify-between">
              <h3 className="text-xs font-bold text-[#6B7A90] uppercase tracking-wider">Cancellation Rate</h3>
              <div>
                <h4 className="text-2xl font-extrabold text-[#9B1C1C]">{reportData.cancellation_rate}%</h4>
                <p className="text-xs text-[#6B7A90] mt-0.5">Business health indicator</p>
              </div>
            </NeumorphicCard>
          </div>

          {/* Section 4: Charts / Graphs */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <NeumorphicCard>
              <h3 className="text-base font-bold text-[#1E2A3A] mb-4">Revenue Trend ($)</h3>
              <div className="h-72 w-full">
                {reportData.chart_data.length === 0 ? (
                  <div className="flex items-center justify-center h-full text-sm text-[#6B7A90]">No revenue trend data found</div>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={reportData.chart_data}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#d0d9e8" />
                      <XAxis dataKey="label" stroke="#6B7A90" fontSize={12} />
                      <YAxis stroke="#6B7A90" fontSize={12} />
                      <Tooltip />
                      <Bar dataKey="revenue" fill="#3E7BFA" radius={[6, 6, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </NeumorphicCard>

            <NeumorphicCard>
              <h3 className="text-base font-bold text-[#1E2A3A] mb-4">Completed Bookings Trend</h3>
              <div className="h-72 w-full">
                {reportData.chart_data.length === 0 ? (
                  <div className="flex items-center justify-center h-full text-sm text-[#6B7A90]">No bookings trend data found</div>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={reportData.chart_data}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#d0d9e8" />
                      <XAxis dataKey="label" stroke="#6B7A90" fontSize={12} />
                      <YAxis stroke="#6B7A90" fontSize={12} />
                      <Tooltip />
                      <Bar dataKey="bookings" fill="#3FBF8F" radius={[6, 6, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </NeumorphicCard>
          </div>
        </>
      )}
    </div>
  );
}