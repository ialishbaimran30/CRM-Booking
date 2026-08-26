import { useEffect, useRef } from 'react';

// Mirrors REACT_APP_API_BASE_URL's host but as a ws:// URL, since the
// backend serves both HTTP and WebSocket on the same Django/Channels process.
const WS_BASE_URL =
  process.env.REACT_APP_WS_BASE_URL ||
  (process.env.REACT_APP_API_BASE_URL || 'http://127.0.0.1:8000/api')
    .replace(/^http/, 'ws')
    .replace(/\/api\/?$/, '');

// Real-time delivery only — every message here corresponds to exactly one
// Notification row already created server-side by
// notifications/services.py::CommunicationService.send_in_app_notification.
// This hook never creates notifications itself, only relays them.
export default function useNotificationSocket(enabled, onNotification) {
  const callbackRef = useRef(onNotification);
  callbackRef.current = onNotification;

  useEffect(() => {
    if (!enabled) return undefined;
    const token = localStorage.getItem('access_token');
    if (!token) return undefined;

    let socket;
    try {
      // M-3: token travels as a WebSocket subprotocol, not a URL query
      // param, so it never ends up in access logs or browser history.
      socket = new WebSocket(`${WS_BASE_URL}/ws/notifications/`, ["jwt", token]);
    } catch (err) {
      console.error('Failed to open notification WebSocket', err);
      return undefined;
    }

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data?.notification) {
          callbackRef.current?.(data.notification);
        }
      } catch (err) {
        console.error('Failed to parse notification WebSocket message', err);
      }
    };

    socket.onerror = (err) => {
      console.error('Notification WebSocket error', err);
    };

    return () => {
      socket.close();
    };
  }, [enabled]);
}
