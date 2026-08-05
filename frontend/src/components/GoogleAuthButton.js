import React from 'react';
import { GoogleLogin } from '@react-oauth/google';
import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL||'http://127.0.0.1:8000/api';

export default function GoogleAuthButton({ onLoginSuccess }) {
  const handleGoogleSuccess = async (credentialResponse) => {
    try {
      const idToken = credentialResponse.credential;

      const response = await axios.post(`${API_BASE_URL}/auth/google/`, {
        id_token: idToken,
      });

      const { access, refresh, user, created } = response.data;

      localStorage.setItem('access_token', access);
      localStorage.setItem('refresh_token', refresh);
      localStorage.setItem('user', JSON.stringify(user));
      
      if (onLoginSuccess) {
        onLoginSuccess(user);
      }
    } catch (error) {
      console.error("Google authentication failed:", error.response?.data || error.message);
      alert(error.response?.data?.detail || "Google Sign-In failed.");
    }
  };

  return (
    <div className="flex justify-center my-4">
      <GoogleLogin
        onSuccess={handleGoogleSuccess}
        onError={() => console.error("Google Sign-In Error")}
      />
    </div>
  );
}