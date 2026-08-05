import React from 'react';

export const FormField = ({ label, error, registration, type = 'text', placeholder, disabled = false }) => {
  return (
    <div className="flex flex-col gap-1.5 mb-4">
      {label && <label className="text-xs font-semibold text-darkText uppercase tracking-wider">{label}</label>}
      <input
        type={type}
        disabled={disabled}
        placeholder={placeholder}
        {...registration}
        className="bg-neumorphicCard shadow-neo-inset px-4 py-3 rounded-xl text-darkText placeholder-lightText focus:outline-none focus:ring-2 focus:ring-primary/50 text-sm transition-all"
      />
      {error && <span className="text-danger text-xs mt-1 font-medium">{error.message}</span>}
    </div>
  );import React from 'react';

export const FormField = ({ label, error, children, className }) => {
  return (
    <div className={`flex flex-col gap-1.5 mb-4 ${className || ''}`}>
      {label && <label className="text-xs font-semibold text-[#1E2A3A] uppercase tracking-wider">{label}</label>}
      {children}
      {error && <span className="text-xs text-[#F0563F] font-medium">{error.message}</span>}
    </div>
  );
};
};