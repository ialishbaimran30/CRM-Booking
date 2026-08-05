import React, { useState, useEffect, useCallback } from 'react';
import { NeumorphicCard } from '../components/common/NeumorphicCard';
import { StatusBadge } from '../components/common/StatusBadge';
import toast from 'react-hot-toast';

export default function PaymentsView() {
  const [invoices, setInvoices] = useState([]);
  const [summary, setSummary] = useState({ total_revenue: 0, total_pending: 0, total_refunded: 0, this_month_revenue: 0 });
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  const [selectedInvoice, setSelectedInvoice] = useState(null);
  const [showActionModal, setShowActionModal] = useState(false);
  const [actionType, setActionType] = useState('PAID');
  const [paymentMethod, setPaymentMethod] = useState('CASH');
  const [applyDiscount, setApplyDiscount] = useState(false);
  const [discountAmount, setDiscountAmount] = useState('');
  const [couponCode, setCouponCode] = useState('');
  const [refundReason, setRefundReason] = useState('');

  const [selectedClient, setSelectedClient] = useState(null);
  const [showClientModal, setShowClientModal] = useState(false);
  const [showInvoiceModal, setShowInvoiceModal] = useState(false);
  const [invoiceToPrint, setInvoiceToPrint] = useState(null);

  const authHeaders = () => ({
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
  });

  const fetchSummary = useCallback(async () => {
    try {
      const res = await fetch('/api/payments/payments/summary/', { headers: authHeaders() });
      if (res.ok) setSummary(await res.json());
    } catch (err) {
      console.error(err);
    }
  }, []);

  const fetchInvoices = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (search) params.set('search', search);
      if (statusFilter) params.set('status', statusFilter);
      if (startDate) params.set('date_from', startDate);
      if (endDate) params.set('date_to', endDate);

      const res = await fetch(`/api/payments/invoices/?${params.toString()}`, { headers: authHeaders() });
      if (!res.ok) throw new Error('Failed to load invoices');
      const data = await res.json();
      let results = (Array.isArray(data) ? data : (data.results || []));
      
      // Client-side date filter safeguard with inclusive end time
      if (startDate || endDate) {
        results = results.filter(inv => {
          const itemDateStr = inv.paid_at ? inv.paid_at.split('T')[0] : (inv.issued_date ? inv.issued_date.split('T')[0] : null);
          if (!itemDateStr) return false;

          const itemTime = new Date(itemDateStr).getTime();
          const startTime = startDate ? new Date(startDate).getTime() : 0;
          const endTime = endDate ? new Date(endDate).setHours(23, 59, 59, 999) : Number.MAX_SAFE_INTEGER;

          return itemTime >= startTime && itemTime <= endTime;
        });
      }
      setInvoices(results);
    } catch (err) {
      console.error(err);
      toast.error('Failed to load payment records.');
      setInvoices([]);
    } finally {
      setLoading(false);
    }
  }, [search, statusFilter, startDate, endDate]);

  useEffect(() => {
    fetchInvoices();
    fetchSummary();
  }, [fetchInvoices, fetchSummary]);

  // Issue 3: Real-Time Synchronization Listener for Payments, Refunds, and Deleted Bookings
  useEffect(() => {
    const handleStorageSync = (e) => {
      if (
        e.key === 'payment_sync_timestamp' || 
        e.key === 'booking_sync_timestamp' || 
        !e.key
      ) {
        fetchInvoices();
        fetchSummary();
      }
    };

    window.addEventListener('storage', handleStorageSync);
    
    const interval = setInterval(() => {
      const syncStamp = localStorage.getItem('payment_sync_timestamp');
      if (syncStamp && syncStamp !== window._lastPaymentSyncStamp) {
        window._lastPaymentSyncStamp = syncStamp;
        fetchInvoices();
        fetchSummary();
      }
    }, 1000);

    return () => {
      window.removeEventListener('storage', handleStorageSync);
      clearInterval(interval);
    };
  }, [fetchInvoices, fetchSummary]);

  const handleOpenActionModal = (invoice, type) => {
    setSelectedInvoice(invoice);
    setActionType(type);
    setPaymentMethod('CASH');
    setApplyDiscount(false);
    setDiscountAmount('');
    setCouponCode('');
    setRefundReason('');
    setShowActionModal(true);
  };

  const handleProcessAction = async (e) => {
    e.preventDefault();
    try {
      const isRefund = actionType === 'REFUND';
      const url = `/api/payments/invoices/${selectedInvoice.id}/${isRefund ? 'refund' : 'pay'}/`;
      const body = isRefund
        ? { refund_reason: refundReason }
        : {
            payment_method: paymentMethod,
            ...(applyDiscount ? { discount_amount: discountAmount || 0, coupon_code: couponCode } : {}),
          };

      const res = await fetch(url, { method: 'POST', headers: authHeaders(), body: JSON.stringify(body) });
      const data = await res.json();

      if (!res.ok) {
        toast.error(data.detail || 'Action failed.');
        return;
      }

      toast.success(isRefund ? 'Payment refunded!' : 'Payment marked as paid!');
      setShowActionModal(false);
      
      // Trigger cross-tab/module synchronization
      localStorage.setItem('payment_sync_timestamp', Date.now().toString());

      fetchInvoices();
      fetchSummary();
    } catch (err) {
      console.error(err);
      toast.error('Something went wrong.');
    }
  };

  const handleDownloadInvoice = (invoice) => {
    setInvoiceToPrint(invoice);
    setShowInvoiceModal(true);
  };

  const printInvoice = () => {
    window.print();
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-[#1E2A3A]">Payment Management</h2>
        <p className="text-sm text-[#6B7A90]">Track invoices, paid transactions, and refund statuses.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <NeumorphicCard className="p-4">
          <p className="text-xs font-bold text-[#6B7A90] uppercase tracking-wider">Total Revenue</p>
          <h3 className="text-2xl font-extrabold text-[#3FBF8F] mt-1">${summary.total_revenue}</h3>
        </NeumorphicCard>
        <NeumorphicCard className="p-4">
          <p className="text-xs font-bold text-[#6B7A90] uppercase tracking-wider">Pending Amount</p>
          <h3 className="text-2xl font-extrabold text-[#E0A800] mt-1">${summary.total_pending}</h3>
        </NeumorphicCard>
        <NeumorphicCard className="p-4">
          <p className="text-xs font-bold text-[#6B7A90] uppercase tracking-wider">Refunded</p>
          <h3 className="text-2xl font-extrabold text-[#9B1C1C] mt-1">${summary.total_refunded}</h3>
        </NeumorphicCard>
        <NeumorphicCard className="p-4">
          <p className="text-xs font-bold text-[#6B7A90] uppercase tracking-wider">This Month's Revenue</p>
          <h3 className="text-2xl font-extrabold text-[#3E7BFA] mt-1">${summary.this_month_revenue}</h3>
        </NeumorphicCard>
      </div>

      <div className="bg-[#F4F7FC] rounded-2xl p-4 shadow-[8px_8px_16px_#d0d9e8,-8px_-8px_16px_#ffffff] flex flex-col lg:flex-row gap-4 items-center justify-between">
        <input
          type="text"
          placeholder="Search by transaction ID, client, or service..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full lg:w-72 bg-[#EEF2F9] border-none rounded-xl px-4 py-2.5 text-sm text-[#1E2A3A] focus:outline-none focus:ring-2 focus:ring-[#3E7BFA]"
        />
        <div className="flex flex-wrap sm:flex-nowrap items-center gap-3 w-full lg:w-auto">
          <div className="flex items-center gap-2 bg-[#EEF2F9] px-3 py-2 rounded-xl">
            <span className="text-xs text-[#6B7A90] font-semibold">From:</span>
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="bg-transparent text-xs text-[#1E2A3A] focus:outline-none cursor-pointer" />
          </div>
          <div className="flex items-center gap-2 bg-[#EEF2F9] px-3 py-2 rounded-xl">
            <span className="text-xs text-[#6B7A90] font-semibold">To:</span>
            <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="bg-transparent text-xs text-[#1E2A3A] focus:outline-none cursor-pointer" />
          </div>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="bg-[#EEF2F9] border-none rounded-xl px-4 py-2.5 text-sm text-[#1E2A3A] font-medium focus:outline-none focus:ring-2 focus:ring-[#3E7BFA]">
            <option value="">All Statuses</option>
            <option value="PAID">Paid</option>
            <option value="UNPAID">Unpaid</option>
            <option value="REFUNDED">Refunded</option>
          </select>
        </div>
      </div>

      <NeumorphicCard className="!p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-[#d0d9e8]/50 text-xs font-bold text-[#6B7A90] uppercase tracking-wider bg-[#EEF2F9]/50">
                <th className="p-4">Transaction ID</th>
                <th className="p-4">Client</th>
                <th className="p-4">Service</th>
                <th className="p-4">Amount</th>
                <th className="p-4">Payment Status</th>
                <th className="p-4">Date</th>
                <th className="p-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#d0d9e8]/30 text-sm text-[#1E2A3A]">
              {loading ? (
                <tr><td colSpan="7" className="text-center py-8 text-[#6B7A90]">Loading transactions...</td></tr>
              ) : invoices.length === 0 ? (
                <tr><td colSpan="7" className="text-center py-8 text-[#6B7A90]">No payment records found.</td></tr>
              ) : (
                invoices.map((inv) => (
                  <tr key={inv.id} className="hover:bg-[#EEF2F9]/30 transition-colors">
                    <td className="p-4 font-semibold text-[#3E7BFA]">{inv.latest_transaction_id}</td>
                    <td className="p-4 font-medium">
                      <button onClick={() => { setSelectedClient(inv); setShowClientModal(true); }} className="text-[#3E7BFA] hover:underline font-semibold cursor-pointer">
                        {inv.client_name}
                      </button>
                    </td>
                    <td className="p-4">{inv.service_name}</td>
                    <td className="p-4 font-bold">${inv.total_amount}</td>
                    <td className="p-4 flex items-center gap-2">
                      <StatusBadge status={inv.status} />
                      {inv.is_overdue && (
                        <span className="bg-[#9B1C1C]/15 text-[#9B1C1C] px-2 py-0.5 rounded-md text-[10px] font-bold">⚠ Overdue</span>
                      )}
                    </td>
                    <td className="p-4">{inv.paid_at ? inv.paid_at.split('T')[0] : '-'}</td>
                    <td className="p-4 text-right space-x-2">
                      <button onClick={() => handleDownloadInvoice(inv)} className="bg-[#3E7BFA]/15 text-[#3E7BFA] px-3 py-1 rounded-lg text-xs font-semibold cursor-pointer">
                        Invoice
                      </button>
                      {inv.status !== 'PAID' && inv.status !== 'REFUNDED' && (
                        <button onClick={() => handleOpenActionModal(inv, 'PAID')} className="bg-[#3FBF8F]/15 text-[#3FBF8F] px-3 py-1 rounded-lg text-xs font-semibold cursor-pointer">
                          Mark Paid
                        </button>
                      )}
                      {inv.status === 'PAID' && (
                        <button onClick={() => handleOpenActionModal(inv, 'REFUND')} className="bg-[#9B1C1C]/15 text-[#9B1C1C] px-3 py-1 rounded-lg text-xs font-semibold cursor-pointer">
                          Refund
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </NeumorphicCard>

      {/* Mark Paid / Refund Modal */}
      {showActionModal && (
        <div className="fixed inset-0 flex justify-center items-center z-50 p-4 bg-black/40">
          <div className="bg-[#F4F7FC] rounded-2xl p-6 w-full max-w-md shadow-xl">
            <h3 className="text-lg font-bold text-[#1E2A3A] mb-4">
              {actionType === 'PAID' ? 'Mark Payment as Paid' : 'Refund Payment'}
            </h3>
            <form onSubmit={handleProcessAction} className="space-y-4">
              {actionType === 'PAID' ? (
                <>
                  <div>
                    <label className="text-xs font-bold text-[#6B7A90] uppercase block mb-1">Payment Method</label>
                    <select value={paymentMethod} onChange={(e) => setPaymentMethod(e.target.value)} className="w-full bg-[#EEF2F9] rounded-xl px-4 py-2 text-sm focus:outline-none">
                      <option value="CASH">Cash</option>
                      <option value="CREDIT_CARD">Credit Card</option>
                      <option value="BANK_TRANSFER">Bank Transfer</option>
                      <option value="JAZZCASH">JazzCash / EasyPaisa</option>
                    </select>
                  </div>

                  <label className="flex items-center gap-2 text-sm text-[#1E2A3A] cursor-pointer">
                    <input type="checkbox" checked={applyDiscount} onChange={(e) => setApplyDiscount(e.target.checked)} />
                    Apply discount / coupon
                  </label>

                  {applyDiscount && (
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs font-bold text-[#6B7A90] uppercase block mb-1">Discount ($)</label>
                        <input type="number" min="0" value={discountAmount} onChange={(e) => setDiscountAmount(e.target.value)} className="w-full bg-[#EEF2F9] rounded-xl px-3 py-2 text-sm focus:outline-none" />
                      </div>
                      <div>
                        <label className="text-xs font-bold text-[#6B7A90] uppercase block mb-1">Coupon Code</label>
                        <input type="text" value={couponCode} onChange={(e) => setCouponCode(e.target.value)} className="w-full bg-[#EEF2F9] rounded-xl px-3 py-2 text-sm focus:outline-none" />
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div>
                  <label className="text-xs font-bold text-[#6B7A90] uppercase block mb-1">Refund Reason</label>
                  <textarea rows="3" value={refundReason} onChange={(e) => setRefundReason(e.target.value)} required className="w-full bg-[#EEF2F9] rounded-xl p-3 text-sm focus:outline-none" placeholder="Enter reason for refund..." />
                </div>
              )}
              <div className="flex justify-end gap-2 mt-4">
                <button type="button" onClick={() => setShowActionModal(false)} className="bg-[#EEF2F9] text-[#6B7A90] px-4 py-2 rounded-xl text-sm font-semibold cursor-pointer">Cancel</button>
                <button type="submit" className="bg-[#3E7BFA] text-white px-4 py-2 rounded-xl text-sm font-semibold cursor-pointer">Confirm</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Client History Modal */}
      {showClientModal && selectedClient && (
        <div className="fixed inset-0 flex justify-center items-center z-50 p-4 bg-black/40">
          <div className="bg-[#F4F7FC] rounded-2xl p-6 w-full max-w-lg shadow-xl space-y-4">
            <div className="flex justify-between items-center">
              <h3 className="text-lg font-bold text-[#1E2A3A]">Client Payment History — {selectedClient.client_name}</h3>
              <button onClick={() => setShowClientModal(false)} className="text-[#6B7A90] font-bold text-lg px-2 cursor-pointer">✕</button>
            </div>
            <div className="max-h-64 overflow-y-auto space-y-2">
              {invoices.filter((i) => i.client_id === selectedClient.client_id).map((i) => (
                <div key={i.id} className="flex justify-between items-center bg-[#EEF2F9]/50 p-3 rounded-xl text-sm">
                  <div>
                    <span className="font-semibold text-[#3E7BFA]">{i.latest_transaction_id}</span>
                    <p className="text-xs text-[#6B7A90]">{i.service_name} • {i.paid_at ? i.paid_at.split('T')[0] : '-'}</p>
                  </div>
                  <div className="text-right">
                    <span className="font-bold">${i.total_amount}</span>
                    <div><StatusBadge status={i.status} /></div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Invoice Print Modal */}
      {showInvoiceModal && invoiceToPrint && (
        <div className="fixed inset-0 flex justify-center items-center z-50 p-4 bg-black/40 print:bg-white">
          <div className="bg-white rounded-2xl p-8 w-full max-w-md shadow-xl" id="invoice-print-area">
            <h2 className="text-xl font-bold text-[#1E2A3A]">Invoice {invoiceToPrint.invoice_number}</h2>
            <p className="text-xs text-[#6B7A90] mb-4">Issued {invoiceToPrint.issued_date?.split('T')[0]}</p>
            <div className="space-y-1 text-sm">
              <p><strong>Client:</strong> {invoiceToPrint.client_name}</p>
              <p><strong>Service:</strong> {invoiceToPrint.service_name}</p>
              <p><strong>Subtotal:</strong> ${invoiceToPrint.subtotal}</p>
              <p><strong>Discount:</strong> ${invoiceToPrint.discount_amount} {invoiceToPrint.coupon_code && `(${invoiceToPrint.coupon_code})`}</p>
              <p><strong>Tax:</strong> ${invoiceToPrint.tax_amount}</p>
              <p className="text-lg font-bold pt-2 border-t mt-2"><strong>Total:</strong> ${invoiceToPrint.total_amount}</p>
              <p><strong>Status:</strong> {invoiceToPrint.status}</p>
            </div>
            <div className="flex justify-end gap-2 mt-6 print:hidden">
              <button onClick={() => setShowInvoiceModal(false)} className="bg-[#EEF2F9] text-[#6B7A90] px-4 py-2 rounded-xl text-sm font-semibold cursor-pointer">Close</button>
              <button onClick={printInvoice} className="bg-[#3E7BFA] text-white px-4 py-2 rounded-xl text-sm font-semibold cursor-pointer">Print / Save PDF</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}