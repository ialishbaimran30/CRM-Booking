import React from 'react';
import { GoogleLogin } from '@react-oauth/google';
import axios from 'axios';
import toast from 'react-hot-toast';
import { notifyApiError } from '../utils/apiError';

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://127.0.0.1:8000/api';

export default function GoogleAuthButton({ onLoginSuccess }) {
  const handleGoogleSuccess = async (credentialResponse) => {
    try {
      const idToken = credentialResponse.credential;

      const response = await axios.post(`${API_BASE_URL}/auth/google/`, {
        id_token: idToken,
      });

      // The backend is the single source of truth for role: it returns `user.role`
      // ('Admin' | 'Booking Manager' | null-for-Client) — the app never asks the
      // visitor to pick one.
      const { access, refresh, user } = response.data;

      localStorage.setItem('access_token', access);
      localStorage.setItem('refresh_token', refresh);
      localStorage.setItem('user', JSON.stringify(user));

      if (onLoginSuccess) {
        onLoginSuccess(user);
      }
    } catch (error) {
      console.error("Google authentication failed:", error.response?.data || error.message);
      notifyApiError(error, "Google Sign-In failed.");
    }
  };

  return (
    <div className="flex items-center justify-center w-full">
      <GoogleLogin
        onSuccess={handleGoogleSuccess}
        onError={() => {
          console.error("Google Sign-In Error");
          toast.error("Google Sign-In failed. Please try again.");
        }}
      />
    </div>
  );
}
