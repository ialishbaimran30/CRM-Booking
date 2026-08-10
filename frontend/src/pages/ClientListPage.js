import React, { useEffect, useState } from 'react';
import { clientService } from '../api/clientService';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { notifyApiError } from '../utils/apiError';

export default function ClientListPage() {
  const [clients, setClients] = useState([]);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [loading, setLoading] = useState(true);

  // Modal & Form State for Create/Edit
  const [showModal, setShowModal] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [currentClientId, setCurrentClientId] = useState(null);
  const [formData, setFormData] = useState({
    full_name: '',
    email: '',
    phone_number: '',
    address: '',
    city: '',
    country: '',
    status: 'ACTIVE',
    notes: '',
  });

  const fetchClients = async () => {
    try {
      setLoading(true);
      const params = {};
      if (search) params.search = search;
      if (status) params.status = status;
      
      const data = await clientService.getClients(params);
      setClients(Array.isArray(data) ? data : (data.results || []));
    } catch (err) {
      console.error("Error fetching clients:", err);
      toast.error("Failed to load clients");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchClients();
  }, [search, status]);

  const handleOpenCreateModal = () => {
    setIsEditing(false);
    setCurrentClientId(null);
    setFormData({
      full_name: '',
      email: '',
      phone_number: '',
      address: '',
      city: '',
      country: '',
      status: 'ACTIVE',
      notes: '',
    });
    setShowModal(true);
  };

  const handleOpenEditModal = (client) => {
    setIsEditing(true);
    setCurrentClientId(client.id);
    setFormData({
      full_name: client.full_name || '',
      email: client.email || '',
      phone_number: client.phone_number || '',
      address: client.address || '',
      city: client.city || '',
      country: client.country || '',
      status: client.status || 'ACTIVE',
      notes: client.notes || '',
    });
    setShowModal(true);
  };

  const validateEmailInput = (inputElement) => {
    const email = inputElement.value;
    if (!email) {
      inputElement.setCustomValidity("Please fill out this field.");
      return;
    }

    const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
    if (!emailRegex.test(email)) {
      inputElement.setCustomValidity("Please enter a valid email address.");
      return;
    }

    const domain = email.split('@')[1]?.toLowerCase();
    const commonTypos = ['gamil.com', 'gmal.com', 'gmai.com', 'gamil.co', 'gmal.co', 'yaho.com', 'hotmai.com'];
    
    if (commonTypos.includes(domain)) {
      inputElement.setCustomValidity(`Please enter a valid email address with correct spelling (e.g., @gmail.com instead of @${domain}).`);
    } else {
      inputElement.setCustomValidity("");
    }
  };

  const handleFormSubmit = async (e) => {
    e.preventDefault();

    try {
      if (isEditing) {
        await clientService.updateClient(currentClientId, formData);
        toast.success("Client updated successfully!");
      } else {
        await clientService.createClient(formData);
        toast.success("Client created successfully!");
      }
      setShowModal(false);
      fetchClients(); // Refreshes list instantly
    } catch (err) {
      console.error("Full Error Response:", err?.response?.data);
      notifyApiError(err, isEditing ? "Failed to update client." : "Failed to create client. Check inputs.");
    }
  };

  const handleDeleteClient = async (clientId, clientName) => {
    if (!window.confirm(`Are you sure you want to delete ${clientName}?`)) return;

    try {
      await clientService.deleteClient(clientId);
      toast.success("Client deleted successfully!");
      fetchClients(); // Refreshes list instantly
    } catch (err) {
      console.error(err);
      notifyApiError(err, "Failed to delete client.");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-[#1E2A3A]">Clients Directory</h1>
          <p className="text-sm text-[#6B7A90]">Manage and view all your CRM clients and history.</p>
        </div>
        <button 
          onClick={handleOpenCreateModal} 
          className="flex items-center gap-2 bg-[#3E7BFA] text-white px-5 py-2.5 rounded-xl font-semibold text-sm shadow-[4px_4px_10px_rgba(62,123,250,0.3)] hover:bg-[#2E63D6] transition-all cursor-pointer"
        >
          + Add New Client
        </button>
      </div>

      {/* Filter & Search Bar */}
      <div className="bg-[#F4F7FC] rounded-2xl p-4 shadow-[8px_8px_16px_#d0d9e8,-8px_-8px_16px_#ffffff] flex flex-col sm:flex-row gap-4 items-center justify-between">
        <input 
          type="text" 
          placeholder="Search by name, email, or phone..." 
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full sm:w-80 bg-[#EEF2F9] border-none rounded-xl px-4 py-2.5 text-sm text-[#1E2A3A] focus:outline-none focus:ring-2 focus:ring-[#3E7BFA]"
        />
        <select 
          value={status} 
          onChange={(e) => setStatus(e.target.value)}
          className="bg-[#EEF2F9] border-none rounded-xl px-4 py-2.5 text-sm text-[#1E2A3A] font-medium focus:outline-none focus:ring-2 focus:ring-[#3E7BFA]"
        >
          <option value="">All Status</option>
          <option value="ACTIVE">Active</option>
          <option value="INACTIVE">Inactive</option>
        </select>
      </div>

      {/* Table Section */}
      <div className="bg-[#F4F7FC] rounded-2xl shadow-[8px_8px_16px_#d0d9e8,-8px_-8px_16px_#ffffff] overflow-hidden">
        {loading ? (
          <div className="text-center py-8 text-[#6B7A90]">Loading clients...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-[#d0d9e8]/50 text-xs font-bold text-[#6B7A90] uppercase tracking-wider bg-[#EEF2F9]/50">
                  <th className="p-4">Client Name</th>
                  <th className="p-4">Email</th>
                  <th className="p-4">Phone</th>
                  <th className="p-4">City</th>
                  <th className="p-4">Status</th>
                  <th className="p-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#d0d9e8]/30 text-sm text-[#1E2A3A]">
                {clients.length > 0 ? clients.map((client) => (
                  <tr key={client.id} className="hover:bg-[#EEF2F9]/30 transition-colors">
                    <td className="p-4 font-bold">
                      <Link to={`/clients/${client.id}`} className="text-[#3E7BFA] hover:underline">
                        {client.full_name}
                      </Link>
                    </td>
                    <td className="p-4 text-[#6B7A90]">{client.email}</td>
                    <td className="p-4 text-[#6B7A90]">{client.phone_number || 'N/A'}</td>
                    <td className="p-4">{client.city || 'N/A'}</td>
                    <td className="p-4">
                      <span className={`px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider ${
                        client.status === 'ACTIVE' 
                          ? 'bg-[#3FBF8F]/15 text-[#3FBF8F]' 
                          : 'bg-[#6B7A90]/15 text-[#6B7A90]'
                      }`}>
                        {client.status || 'ACTIVE'}
                      </span>
                    </td>
                    <td className="p-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Link 
                          to={`/clients/${client.id}`} 
                          className="bg-[#EEF2F9] text-[#3E7BFA] px-3 py-1.5 rounded-xl font-semibold text-xs shadow-[3px_3px_6px_#d0d9e8,-3px_-3px_6px_#ffffff] hover:shadow-[1px_1px_3px_#d0d9e8,-1px_-1px_3px_#ffffff] transition-all"
                        >
                          View
                        </Link>
                        <button 
                          onClick={() => handleOpenEditModal(client)} 
                          className="bg-[#EEF2F9] text-[#3E7BFA] px-3 py-1.5 rounded-xl font-semibold text-xs shadow-[3px_3px_6px_#d0d9e8,-3px_-3px_6px_#ffffff] hover:shadow-[1px_1px_3px_#d0d9e8,-1px_-1px_3px_#ffffff] transition-all cursor-pointer"
                        >
                          Edit
                        </button>
                        <button 
                          onClick={() => handleDeleteClient(client.id, client.full_name)} 
                          className="bg-[#FDE8E8] text-[#9B1C1C] px-3 py-1.5 rounded-xl font-semibold text-xs shadow-[3px_3px_6px_#d0d9e8,-3px_-3px_6px_#ffffff] hover:bg-[#F8D7D7] transition-all cursor-pointer"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan="6" className="text-center py-8 text-[#6B7A90]">No clients found.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add / Edit Client Modal */}
      {showModal && (
        <div className="fixed inset-0 flex justify-center items-center z-50 p-4 bg-transparent pointer-events-none">
          <div className="bg-[#F4F7FC] rounded-2xl p-6 w-full max-w-lg shadow-[12px_12px_24px_#d0d9e8,-12px_-12px_24px_#ffffff] pointer-events-auto">
            <h2 className="text-xl font-bold text-[#1E2A3A] mb-4">
              {isEditing ? 'Edit Client Details' : 'Add New Client'}
            </h2>
            <form onSubmit={handleFormSubmit} className="flex flex-col gap-4">
              <div>
                <label className="text-xs font-bold text-[#6B7A90] uppercase tracking-wider mb-1.5 block">Full Name *</label>
                <input 
                  type="text" 
                  required 
                  maxLength={255}
                  value={formData.full_name} 
                  onChange={(e) => setFormData({...formData, full_name: e.target.value})} 
                  className="w-full bg-[#EEF2F9] border-none rounded-xl px-4 py-2.5 text-sm text-[#1E2A3A] focus:outline-none focus:ring-2 focus:ring-[#3E7BFA]" 
                />
              </div>
              <div>
                <label className="text-xs font-bold text-[#6B7A90] uppercase tracking-wider mb-1.5 block">Email Address *</label>
                <input 
                  type="email" 
                  required 
                  maxLength={255}
                  value={formData.email} 
                  onInput={(e) => validateEmailInput(e.target)}
                  onChange={(e) => {
                    setFormData({...formData, email: e.target.value});
                    validateEmailInput(e.target);
                  }} 
                  className="w-full bg-[#EEF2F9] border-none rounded-xl px-4 py-2.5 text-sm text-[#1E2A3A] focus:outline-none focus:ring-2 focus:ring-[#3E7BFA]" 
                />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-bold text-[#6B7A90] uppercase tracking-wider mb-1.5 block">Phone Number</label>
                  <input 
                    type="text" 
                    maxLength={255}
                    value={formData.phone_number} 
                    onChange={(e) => setFormData({...formData, phone_number: e.target.value})} 
                    className="w-full bg-[#EEF2F9] border-none rounded-xl px-4 py-2.5 text-sm text-[#1E2A3A] focus:outline-none focus:ring-2 focus:ring-[#3E7BFA]" 
                  />
                </div>
                <div>
                  <label className="text-xs font-bold text-[#6B7A90] uppercase tracking-wider mb-1.5 block">Status</label>
                  <select 
                    value={formData.status} 
                    onChange={(e) => setFormData({...formData, status: e.target.value})} 
                    className="w-full bg-[#EEF2F9] border-none rounded-xl px-4 py-2.5 text-sm text-[#1E2A3A] focus:outline-none focus:ring-2 focus:ring-[#3E7BFA]"
                  >
                    <option value="ACTIVE">Active</option>
                    <option value="INACTIVE">Inactive</option>
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-bold text-[#6B7A90] uppercase tracking-wider mb-1.5 block">City</label>
                  <input 
                    type="text" 
                    maxLength={255}
                    value={formData.city} 
                    onChange={(e) => setFormData({...formData, city: e.target.value})} 
                    className="w-full bg-[#EEF2F9] border-none rounded-xl px-4 py-2.5 text-sm text-[#1E2A3A] focus:outline-none focus:ring-2 focus:ring-[#3E7BFA]" 
                  />
                </div>
                <div>
                  <label className="text-xs font-bold text-[#6B7A90] uppercase tracking-wider mb-1.5 block">Country</label>
                  <input 
                    type="text" 
                    maxLength={255}
                    value={formData.country} 
                    onChange={(e) => setFormData({...formData, country: e.target.value})} 
                    className="w-full bg-[#EEF2F9] border-none rounded-xl px-4 py-2.5 text-sm text-[#1E2A3A] focus:outline-none focus:ring-2 focus:ring-[#3E7BFA]" 
                  />
                </div>
              </div>
              <div className="flex gap-3 justify-end mt-2">
                <button 
                  type="button" 
                  onClick={() => setShowModal(false)} 
                  className="bg-[#EEF2F9] text-[#6B7A90] px-4 py-2 rounded-xl font-semibold text-sm shadow-[3px_3px_6px_#d0d9e8,-3px_-3px_6px_#ffffff] hover:text-[#1E2A3A] transition-all cursor-pointer"
                >
                  Cancel
                </button>
                <button 
                  type="submit" 
                  className="bg-[#3E7BFA] text-white px-5 py-2 rounded-xl font-semibold text-sm shadow-[4px_4px_10px_rgba(62,123,250,0.3)] hover:bg-[#2E63D6] transition-all cursor-pointer"
                >
                  {isEditing ? 'Update Client' : 'Save Client'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}