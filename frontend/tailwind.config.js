/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        spine: {
          900: '#0B0F17',
          800: '#111827',
          700: '#1F2937',
          600: '#374151',
          accent: '#3B82F6',
          critical: '#EF4444',
          warning: '#F59E0B',
          success: '#10B981'
        }
      }
    },
  },
  plugins: [],
}
