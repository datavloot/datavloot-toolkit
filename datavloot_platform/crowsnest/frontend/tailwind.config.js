/** @type {import('tailwindcss').Config} */
// Colours are CSS variables (defaults in app/globals.css), so a project's
// branding/ can replace them at runtime; see routes/branding.py.
const v = (name) => `rgb(var(--cn-${name}) / <alpha-value>)`;

module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Geist', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['"Geist Mono"', 'monospace'],
      },
      colors: {
        datavloot: {
          50:  v('accent-50'),    // accent-bg — active sidebar bg
          100: v('accent-100'),   // bg-soft
          200: v('accent-200'),   // border-soft
          400: v('accent-400'),
          600: v('accent-600'),   // accent — logo bg, active elements, spinner
          700: v('accent-700'),   // accent dark
          800: v('accent-800'),   // navy — active sidebar text
          900: v('accent-900'),   // navy-2
        },
        surface: {
          0: '#ffffff',           // bg-elevated — cards, sidebar
          1: v('surface-1'),      // bg — page background
          2: v('surface-2'),      // bg-soft — hover states
          3: v('surface-3'),      // border — dividers
        },
        ink: {
          0: v('ink-0'),          // text
          1: v('ink-1'),          // text intermediate
          2: v('ink-2'),          // text-muted
          3: v('ink-3'),          // text-dim
        },
        warm: {
          DEFAULT: '#D8A021',
          soft: '#f0d27e',
          bg: '#fbeed1',
        },
        wood: {
          DEFAULT: '#A96F4A',
          soft: '#c9a187',
          bg: '#f5e6d8',
          grain: '#7d4e30',
        },
      },
    },
  },
  plugins: [],
};
