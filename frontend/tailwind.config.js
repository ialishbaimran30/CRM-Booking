/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        neumorphicBg: '#EEF2F9',
        neumorphicCard: '#F4F7FC',
        primary: {
          DEFAULT: '#3E7BFA',
          hover: '#2E63D6',
        },
        success: '#3FBF8F',
        warning: '#F2A93C',
        danger: '#F0563F',
        darkText: '#1E2A3A',
        lightText: '#6B7A90',
      },
      boxShadow: {
        neo: '8px 8px 16px #d1d9e6, -8px -8px 16px #ffffff',
        'neo-inset': 'inset 4px 4px 8px #d1d9e6, inset -4px -4px 8px #ffffff',
        'neo-sm': '4px 4px 8px #d1d9e6, -4px -4px 8px #ffffff',
      },
      borderRadius: {
        xl: '1rem',
        '2xl': '1.25rem',
      }
    },
  },
  plugins: [],
}