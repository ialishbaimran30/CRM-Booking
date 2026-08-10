import React, { useEffect, useState } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import OtpInput from './OtpInput';
import { extractErrorMessage, notifyApiError } from '../utils/apiError';

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://127.0.0.1:8000/api';

// Mirrors EmailOTP.RESEND_COOLDOWN_SECONDS in backend/accounts/models.py.
const DEFAULT_RESEND_COOLDOWN = 60;

const isValidEmail = (value) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);

export default function EmailOtpForm({ onLoginSuccess }) {
  const [step, setStep] = useState('email'); // 'email' | 'code'
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [requesting, setRequesting] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [codeError, setCodeError] = useState('');
  const [cooldown, setCooldown] = useState(0);

  useEffect(() => {
    if (cooldown <= 0) return undefined;
    const timer = setInterval(() => setCooldown((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(timer);
  }, [cooldown]);

  const requestCode = async (e) => {
    e?.preventDefault();
    if (!isValidEmail(email)) {
      toast.error('Please enter a valid email address.');
      return;
    }
    setRequesting(true);
    try {
      await axios.post(`${API_BASE_URL}/auth/otp/request/`, { email });
      toast.success('Verification code sent.');
      setStep('code');
      setCode('');
      setCodeError('');
      setCooldown(DEFAULT_RESEND_COOLDOWN);
    } catch (error) {
      const retryAfter = error.response?.data?.retry_after;
      if (error.response?.status === 429 && retryAfter) {
        setStep('code');
        setCooldown(retryAfter);
      }
      notifyApiError(error, 'Failed to send verification code.');
    } finally {
      setRequesting(false);
    }
  };

  const handleVerify = async (fullCode) => {
    setVerifying(true);
    setCodeError('');
    try {
      const response = await axios.post(`${API_BASE_URL}/auth/otp/verify/`, {
        email,
        code: fullCode,
      });
      // The backend is the single source of truth for role: it returns `user.role`
      // ('Admin' | 'Booking Manager' | null-for-Client) — the app never asks the
      // visitor to pick one.
      const { access, refresh, user } = response.data;

      localStorage.setItem('access_token', access);
      localStorage.setItem('refresh_token', refresh);
      localStorage.setItem('user', JSON.stringify(user));

      onLoginSuccess?.(user);
    } catch (error) {
      const message = extractErrorMessage(error.response?.data, 'Incorrect code.');
      setCodeError(message);
      setCode('');
      notifyApiError(error, 'Verification failed.');
    } finally {
      setVerifying(false);
    }
  };

  if (step === 'email') {
    return (
      <form onSubmit={requestCode} className="w-full space-y-3" noValidate>
        <label htmlFor="auth-email" className="sr-only">
          Email address
        </label>
        <input
          id="auth-email"
          type="email"
          required
          autoComplete="email"
          placeholder="you@example.com"
          value={email}
          disabled={requesting}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full bg-neumorphicBg border-none p-3 rounded-xl text-sm text-darkText focus:ring-2 focus:ring-primary outline-none transition disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={requesting}
          className="w-full px-4 py-2.5 bg-primary text-white hover:bg-primary-hover rounded-xl text-sm font-medium transition shadow-neo-sm disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {requesting ? 'Sending…' : 'Continue with Email'}
        </button>
      </form>
    );
  }

  return (
    <div className="w-full space-y-4">
      <p className="text-sm text-lightText">
        Enter the 6-digit code sent to <span className="font-medium text-darkText">{email}</span>
      </p>

      <OtpInput length={6} value={code} onChange={setCode} onComplete={handleVerify} disabled={verifying} error={!!codeError} />

      {codeError && (
        <p role="alert" aria-live="polite" className="text-danger text-xs text-center">
          {codeError}
        </p>
      )}

      <button
        type="button"
        onClick={() => handleVerify(code)}
        disabled={code.length < 6 || verifying}
        className="w-full px-4 py-2.5 bg-primary text-white hover:bg-primary-hover rounded-xl text-sm font-medium transition shadow-neo-sm disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {verifying ? 'Verifying…' : 'Verify'}
      </button>

      <div className="flex items-center justify-between text-xs">
        <button
          type="button"
          onClick={() => {
            setStep('email');
            setCode('');
            setCodeError('');
          }}
          className="text-lightText hover:text-darkText transition"
        >
          Change email
        </button>
        <button
          type="button"
          onClick={requestCode}
          disabled={cooldown > 0 || requesting}
          className="text-primary hover:text-primary-hover font-medium transition disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {cooldown > 0 ? `Resend code (${cooldown}s)` : 'Resend code'}
        </button>
      </div>
    </div>
  );
}
