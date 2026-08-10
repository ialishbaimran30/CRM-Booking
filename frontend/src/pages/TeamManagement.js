import React, { useEffect, useState } from 'react';
import api from '../api/axiosInstance'; // Adjust path to match your axios instance file
import toast from 'react-hot-toast';
import { notifyApiError } from '../utils/apiError';

const DUMMY_USER_ID_FLOOR = 99;

function SearchableUserPicker({ users, selectedUserId, onSelect, query, onQueryChange }) {
  const filteredUsers = users.filter((u) => {
    const fullName = (u.full_name || '').toLowerCase();
    const email = (u.email || '').toLowerCase();
    const q = query.toLowerCase();
    return fullName.includes(q) || email.includes(q);
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', alignItems: 'center', maxWidth: '280px', margin: '0 auto' }}>
      <input
        type="text"
        placeholder="Search user by name or email..."
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        style={{ width: '100%', padding: '6px 10px', borderRadius: '4px', border: '1px solid #ced4da', fontSize: '13px' }}
      />
      <select
        value={selectedUserId}
        onChange={(e) => onSelect(e.target.value)}
        size={filteredUsers.length > 0 ? Math.min(filteredUsers.length + 1, 5) : 2}
        style={{ width: '100%', padding: '6px', borderRadius: '4px', border: '1px solid #ced4da', fontSize: '13px', background: '#fff' }}
      >
        <option value="">-- Select User --</option>
        {filteredUsers.map((u) => (
          <option key={u.id} value={u.id}>
            {u.full_name || u.email} ({u.email})
          </option>
        ))}
      </select>
    </div>
  );
}

export default function TeamManagement() {
  const [roles, setRoles] = useState([]);
  const [users, setUsers] = useState([]);
  const [currentUserId, setCurrentUserId] = useState(null);

  // 'admin' | { type: 'change', roleId } | 'add' | null
  const [editing, setEditing] = useState(null);
  const [selectedUserId, setSelectedUserId] = useState('');
  const [userSearchQuery, setUserSearchQuery] = useState('');

  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError('');

      // Get current user ID directly from localStorage to avoid 404 network errors
      const storedUser = JSON.parse(localStorage.getItem('user') || '{}');
      if (storedUser.id) {
        setCurrentUserId(storedUser.id);
      }

      const rolesRes = await api.get('/accounts/team-roles/');
      let usersRes = await api.get('/accounts/team-roles/available_users/');

      let usersList = usersRes.data || [];

      // Automatically inject dummy users for development/testing if user list is small
      if (usersList.length <= 1) {
        const dummyUsers = [
          { id: 99, full_name: "Ahmad Khan", email: "ahmad@gmail.com" },
          { id: 100, full_name: "Sara Ali", email: "sara@gmail.com" },
          { id: 101, full_name: "Daniyal Ahmed", email: "daniyal@gmail.com" },
          { id: 102, full_name: "Fatima Noor", email: "fatima@gmail.com" },
          { id: 103, full_name: "Ali Raza", email: "ali@gmail.com" },
          { id: 104, full_name: "Hina Malik", email: "hina@gmail.com" },
          { id: 105, full_name: "Zain Hassan", email: "zain@gmail.com" }
        ];
        // Combine real user(s) with dummy users safely
        const existingIds = new Set(usersList.map(u => u.id));
        const filteredDummy = dummyUsers.filter(du => !existingIds.has(du.id));
        usersList = [...usersList, ...filteredDummy];
      }

      setRoles(rolesRes.data);
      setUsers(usersList);
    } catch (err) {
      setError('Failed to load team management data.');
      notifyApiError(err, 'Failed to load team management data.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const adminRole = roles.find((r) => r.role_name === 'Admin');
  const bookingManagers = roles.filter((r) => r.role_name === 'Booking Manager');
  // Only the current Admin may transfer Admin ownership or manage Booking Managers.
  const isCurrentUserAdmin = adminRole?.assigned_user_id === currentUserId;

  const resetEditing = () => {
    setEditing(null);
    setSelectedUserId('');
    setUserSearchQuery('');
  };

  const guardDummyUser = () => {
    const numericUserId = selectedUserId ? parseInt(selectedUserId, 10) : null;
    if (numericUserId >= DUMMY_USER_ID_FLOOR) {
      toast.error('Dummy users are for testing UI preview only and cannot be saved to the backend database.');
      return null;
    }
    return numericUserId;
  };

  const handleTransferAdmin = async () => {
    const numericUserId = guardDummyUser();
    if (numericUserId === null) return;
    try {
      setSaving(true);
      setError('');
      await api.patch(`/accounts/team-roles/${adminRole.id}/`, { assigned_user_id: numericUserId });
      toast.success('Admin ownership transferred successfully!');
      resetEditing();
      fetchData();
    } catch (err) {
      const message = err.response?.data?.role_name?.[0] || err.response?.data?.detail || 'Unauthorized: only the current Admin can transfer ownership.';
      setError(message);
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  const handleChangeBookingManager = async (roleId) => {
    const numericUserId = guardDummyUser();
    if (numericUserId === null) return;
    try {
      setSaving(true);
      setError('');
      await api.patch(`/accounts/team-roles/${roleId}/`, { assigned_user_id: numericUserId });
      toast.success('Booking Manager updated successfully!');
      resetEditing();
      fetchData();
    } catch (err) {
      const message = err.response?.data?.assigned_user_id?.[0] || err.response?.data?.detail || 'Unauthorized: only the current Admin can update Booking Managers.';
      setError(message);
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  const handleAddBookingManager = async () => {
    const numericUserId = guardDummyUser();
    if (!numericUserId) {
      toast.error('Select a user to assign as Booking Manager.');
      return;
    }
    try {
      setSaving(true);
      setError('');
      await api.post('/accounts/team-roles/', { role_name: 'Booking Manager', assigned_user_id: numericUserId });
      toast.success('Booking Manager assigned successfully!');
      resetEditing();
      fetchData();
    } catch (err) {
      const message = err.response?.data?.assigned_user_id?.[0] || err.response?.data?.detail || 'Unauthorized: only the current Admin can assign Booking Managers.';
      setError(message);
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  const handleRemoveBookingManager = async (roleId) => {
    try {
      setSaving(true);
      setError('');
      await api.delete(`/accounts/team-roles/${roleId}/`);
      toast.success('Booking Manager access removed.');
      fetchData();
    } catch (err) {
      const message = err.response?.data?.detail || 'Unauthorized: only the current Admin can remove Booking Managers.';
      setError(message);
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div style={{ padding: '20px', textAlign: 'center', fontFamily: 'Arial, sans-serif' }}>Loading Team Management...</div>;

  const cardStyle = { background: '#fff', borderRadius: '8px', boxShadow: '0 2px 4px rgba(0,0,0,0.05)', overflow: 'hidden', border: '1px solid #e0e0e0' };
  const thStyle = { padding: '14px 16px', color: '#495057', fontSize: '14px' };

  return (
    <div style={{ padding: '30px', maxWidth: '1000px', margin: '0 auto', fontFamily: 'Arial, sans-serif' }}>
      <div style={{ marginBottom: '20px' }}>
        <h2 style={{ margin: '0 0 5px 0', color: '#1E2A3A' }}>Team Management</h2>
        <p style={{ color: '#666', margin: 0 }}>Transfer Admin ownership and manage Booking Managers.</p>
      </div>

      {error && <div style={{ background: '#ffebee', color: '#c62828', padding: '12px', marginBottom: '20px', borderRadius: '6px', border: '1px solid #ffcdd2' }}>{error}</div>}

      {/* Admin */}
      <div style={{ ...cardStyle, marginBottom: '24px' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', background: '#fff' }}>
          <thead>
            <tr style={{ background: '#f8f9fa', textAlign: 'left', borderBottom: '2px solid #e9ecef' }}>
              <th style={thStyle}>Role</th>
              <th style={thStyle}>Assigned To</th>
              <th style={thStyle}>Email</th>
              <th style={{ ...thStyle, textAlign: 'center' }}>Action</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td style={{ padding: '14px 16px', fontWeight: '500', color: '#212529' }}>Admin</td>
              <td style={{ padding: '14px 16px', color: '#495057' }}>{adminRole?.assigned_user_name || 'Unassigned'}</td>
              <td style={{ padding: '14px 16px', color: '#6c757d' }}>{adminRole?.assigned_user_email || '—'}</td>
              <td style={{ padding: '14px 16px', textAlign: 'center' }}>
                {!isCurrentUserAdmin ? (
                  <span title="Read-only: only the current Admin can transfer ownership" style={{ cursor: 'not-allowed', fontSize: '16px' }}>🔒</span>
                ) : editing === 'admin' ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', alignItems: 'center' }}>
                    <SearchableUserPicker users={users} selectedUserId={selectedUserId} onSelect={setSelectedUserId} query={userSearchQuery} onQueryChange={setUserSearchQuery} />
                    <div style={{ display: 'flex', gap: '6px', width: '100%', maxWidth: '280px' }}>
                      <button onClick={handleTransferAdmin} disabled={saving} style={{ flex: 1, background: '#28a745', color: '#fff', border: 'none', padding: '6px 10px', cursor: saving ? 'not-allowed' : 'pointer', borderRadius: '4px', fontWeight: '500', opacity: saving ? 0.7 : 1 }}>
                        {saving ? 'Saving...' : 'Save'}
                      </button>
                      <button onClick={resetEditing} disabled={saving} style={{ flex: 1, background: '#6c757d', color: '#fff', border: 'none', padding: '6px 10px', cursor: 'pointer', borderRadius: '4px', fontWeight: '500' }}>
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <button onClick={() => setEditing('admin')} style={{ background: '#007bff', color: '#fff', border: 'none', padding: '6px 14px', cursor: 'pointer', borderRadius: '4px', fontWeight: '500' }} title="Transfer Admin Ownership">
                    ✏️ Transfer
                  </button>
                )}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Booking Managers */}
      <div style={cardStyle}>
        <table style={{ width: '100%', borderCollapse: 'collapse', background: '#fff' }}>
          <thead>
            <tr style={{ background: '#f8f9fa', textAlign: 'left', borderBottom: '2px solid #e9ecef' }}>
              <th style={thStyle}>Role</th>
              <th style={thStyle}>Assigned To</th>
              <th style={thStyle}>Email</th>
              <th style={{ ...thStyle, textAlign: 'center' }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {bookingManagers.length === 0 && editing !== 'add' && (
              <tr>
                <td colSpan={4} style={{ padding: '14px 16px', color: '#6c757d', textAlign: 'center' }}>
                  No Booking Managers assigned yet.
                </td>
              </tr>
            )}
            {bookingManagers.map((role) => {
              const isEditingRow = editing?.type === 'change' && editing.roleId === role.id;
              return (
                <tr key={role.id} style={{ borderBottom: '1px solid #e9ecef' }}>
                  <td style={{ padding: '14px 16px', fontWeight: '500', color: '#212529' }}>Booking Manager</td>
                  <td style={{ padding: '14px 16px', color: '#495057' }}>{role.assigned_user_name || 'Unassigned'}</td>
                  <td style={{ padding: '14px 16px', color: '#6c757d' }}>{role.assigned_user_email || '—'}</td>
                  <td style={{ padding: '14px 16px', textAlign: 'center' }}>
                    {!isCurrentUserAdmin ? (
                      <span title="Read-only: only the current Admin can manage Booking Managers" style={{ cursor: 'not-allowed', fontSize: '16px' }}>🔒</span>
                    ) : isEditingRow ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', alignItems: 'center' }}>
                        <SearchableUserPicker users={users} selectedUserId={selectedUserId} onSelect={setSelectedUserId} query={userSearchQuery} onQueryChange={setUserSearchQuery} />
                        <div style={{ display: 'flex', gap: '6px', width: '100%', maxWidth: '280px' }}>
                          <button onClick={() => handleChangeBookingManager(role.id)} disabled={saving} style={{ flex: 1, background: '#28a745', color: '#fff', border: 'none', padding: '6px 10px', cursor: saving ? 'not-allowed' : 'pointer', borderRadius: '4px', fontWeight: '500', opacity: saving ? 0.7 : 1 }}>
                            {saving ? 'Saving...' : 'Save'}
                          </button>
                          <button onClick={resetEditing} disabled={saving} style={{ flex: 1, background: '#6c757d', color: '#fff', border: 'none', padding: '6px 10px', cursor: 'pointer', borderRadius: '4px', fontWeight: '500' }}>
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div style={{ display: 'flex', gap: '8px', justifyContent: 'center' }}>
                        <button
                          onClick={() => { setEditing({ type: 'change', roleId: role.id }); setSelectedUserId(''); setUserSearchQuery(''); }}
                          style={{ background: '#007bff', color: '#fff', border: 'none', padding: '6px 14px', cursor: 'pointer', borderRadius: '4px', fontWeight: '500' }}
                          title="Change this Booking Manager to another user"
                        >
                          ✏️ Change
                        </button>
                        <button
                          onClick={() => handleRemoveBookingManager(role.id)}
                          disabled={saving}
                          style={{ background: '#dc3545', color: '#fff', border: 'none', padding: '6px 14px', cursor: saving ? 'not-allowed' : 'pointer', borderRadius: '4px', fontWeight: '500', opacity: saving ? 0.7 : 1 }}
                          title="Remove Booking Manager access"
                        >
                          🗑️ Remove
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}

            {isCurrentUserAdmin && (
              <tr>
                <td style={{ padding: '14px 16px', fontWeight: '500', color: '#212529' }}>Booking Manager</td>
                <td colSpan={editing === 'add' ? 1 : 2} style={{ padding: '14px 16px', color: '#6c757d' }}>
                  {editing !== 'add' && 'New assignment'}
                </td>
                {editing !== 'add' && <td />}
                <td style={{ padding: '14px 16px', textAlign: 'center' }}>
                  {editing === 'add' ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', alignItems: 'center' }}>
                      <SearchableUserPicker users={users} selectedUserId={selectedUserId} onSelect={setSelectedUserId} query={userSearchQuery} onQueryChange={setUserSearchQuery} />
                      <div style={{ display: 'flex', gap: '6px', width: '100%', maxWidth: '280px' }}>
                        <button onClick={handleAddBookingManager} disabled={saving} style={{ flex: 1, background: '#28a745', color: '#fff', border: 'none', padding: '6px 10px', cursor: saving ? 'not-allowed' : 'pointer', borderRadius: '4px', fontWeight: '500', opacity: saving ? 0.7 : 1 }}>
                          {saving ? 'Saving...' : 'Save'}
                        </button>
                        <button onClick={resetEditing} disabled={saving} style={{ flex: 1, background: '#6c757d', color: '#fff', border: 'none', padding: '6px 10px', cursor: 'pointer', borderRadius: '4px', fontWeight: '500' }}>
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button
                      onClick={() => { setEditing('add'); setSelectedUserId(''); setUserSearchQuery(''); }}
                      style={{ background: '#007bff', color: '#fff', border: 'none', padding: '6px 14px', cursor: 'pointer', borderRadius: '4px', fontWeight: '500' }}
                      title="Assign a new Booking Manager"
                    >
                      ➕ Add Booking Manager
                    </button>
                  )}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
