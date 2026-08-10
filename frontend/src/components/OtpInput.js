import React, { useEffect, useRef } from 'react';

/**
 * A row of single-digit boxes for entering a numeric OTP code, with
 * auto-advance, backspace-to-previous, and paste-distribution support.
 */
export default function OtpInput({
  length = 6,
  value,
  onChange,
  onComplete,
  disabled = false,
  error = false,
  autoFocus = true,
}) {
  const inputRefs = useRef([]);

  useEffect(() => {
    if (autoFocus && value === '') {
      inputRefs.current[0]?.focus();
    }
  }, [value, autoFocus]);

  const setDigit = (index, digit) => {
    const digits = value.split('');
    digits[index] = digit;
    const next = digits.join('').slice(0, length);
    onChange(next);
    if (digit && index < length - 1) {
      inputRefs.current[index + 1]?.focus();
    }
    if (next.length === length) {
      onComplete?.(next);
    }
  };

  const handleChange = (index, e) => {
    const raw = e.target.value.replace(/\D/g, '');
    if (!raw) {
      setDigit(index, '');
      return;
    }
    setDigit(index, raw[raw.length - 1]);
  };

  const handleKeyDown = (index, e) => {
    if (e.key === 'Backspace') {
      if (value[index]) {
        setDigit(index, '');
      } else if (index > 0) {
        inputRefs.current[index - 1]?.focus();
        setDigit(index - 1, '');
      }
    } else if (e.key === 'ArrowLeft' && index > 0) {
      inputRefs.current[index - 1]?.focus();
    } else if (e.key === 'ArrowRight' && index < length - 1) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handlePaste = (e) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, length);
    if (!pasted) return;
    onChange(pasted);
    const focusIndex = Math.min(pasted.length, length - 1);
    inputRefs.current[focusIndex]?.focus();
    if (pasted.length === length) {
      onComplete?.(pasted);
    }
  };

  return (
    <div className="flex gap-1.5 sm:gap-3 justify-center" role="group" aria-label="Verification code">
      {Array.from({ length }).map((_, index) => (
        <input
          key={index}
          ref={(el) => (inputRefs.current[index] = el)}
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          maxLength={1}
          autoComplete={index === 0 ? 'one-time-code' : 'off'}
          aria-label={`Digit ${index + 1} of ${length}`}
          value={value[index] || ''}
          disabled={disabled}
          onChange={(e) => handleChange(index, e)}
          onKeyDown={(e) => handleKeyDown(index, e)}
          onPaste={handlePaste}
          className={`w-9 h-10 sm:w-12 sm:h-14 text-base sm:text-lg text-center font-semibold rounded-xl bg-neumorphicBg border-none text-darkText outline-none transition focus:ring-2 focus:ring-primary disabled:opacity-50 disabled:cursor-not-allowed ${
            error ? 'ring-2 ring-danger' : ''
          }`}
        />
      ))}
    </div>
  );
}
