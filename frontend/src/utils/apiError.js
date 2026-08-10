import toast from 'react-hot-toast';

/**
 * Pull a single human-readable message out of a DRF-style error payload,
 * e.g. {"detail": "..."} or {"field": ["msg"]} or {"non_field_errors": ["msg"]}.
 */
export function extractErrorMessage(data, fallback = 'Something went wrong.') {
  if (!data) return fallback;
  if (typeof data === 'string') return data;
  if (typeof data.detail === 'string') return data.detail;

  const firstKey = Object.keys(data)[0];
  const value = firstKey ? data[firstKey] : null;
  const message = Array.isArray(value) ? value[0] : value;
  return typeof message === 'string' ? message : fallback;
}

/**
 * Show a toast for a failed axios request, covering validation, auth, and
 * network errors with a single consistent code path.
 */
export function notifyApiError(err, fallback = 'Something went wrong.') {
  if (err?.response) {
    toast.error(extractErrorMessage(err.response.data, fallback));
  } else {
    toast.error('Network error. Please check your connection and try again.');
  }
}
