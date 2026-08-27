import React, { useState } from 'react';
import GoogleAuthButton from './GoogleAuthButton';
import EmailOtpForm from './EmailOtpForm';

export default function AuthScreen({ onLoginSuccess }) {
  const [mode, setMode] = useState('signin'); // 'signin' | 'signup'

  const isSignUp = mode === 'signup';

  return (
    <div className="min-h-screen bg-neumorphicBg flex items-center justify-center p-4">
      <div className="bg-neumorphicCard p-6 sm:p-8 rounded-2xl shadow-neo w-full max-w-md text-center border border-[#d0d9e8]/50">
        <h1 className="text-2xl font-bold mb-1 text-darkText">
          {isSignUp ? 'Create your account' : 'Welcome back'}
        </h1>
        <p className="text-lightText text-sm mb-6">
          {isSignUp
            ? 'Sign up to access the CRM & Booking Portal'
            : 'Sign in to the CRM & Booking Portal'}
        </p>

        <div className="flex flex-col items-center gap-4">
          <GoogleAuthButton onLoginSuccess={onLoginSuccess} />

          <div className="flex items-center w-full gap-3">
            <div className="flex-1 border-t border-[#d0d9e8]" />
            <span className="text-lightText text-xs uppercase tracking-wider">or</span>
            <div className="flex-1 border-t border-[#d0d9e8]" />
          </div>

          <EmailOtpForm onLoginSuccess={onLoginSuccess} purpose={isSignUp ? 'signup' : 'login'} />
        </div>

        <button
          type="button"
          onClick={() => setMode(isSignUp ? 'signin' : 'signup')}
          className="mt-6 text-primary hover:text-primary-hover text-sm font-medium hover:underline transition"
        >
          {isSignUp ? 'Already have an account? Sign in' : "Don't have an account? Sign up"}
        </button>
      </div>
    </div>
  );
}
