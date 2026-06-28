/** @type {import('tailwindcss').Config} */
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
          50:  '#e3eff3',   // accent-bg — active sidebar bg
          100: '#B8DAF0',   // bg-soft
          200: '#A8D4E8',   // border-soft
          600: '#2C80A5',   // accent — logo bg, active elements, spinner
          700: '#1f6a8a',   // accent dark
          800: '#1a3a4a',   // navy — active sidebar text
          900: '#0f2735',   // navy-2
        },
        surface: {
          0: '#ffffff',     // bg-elevated — cards, sidebar
          1: '#D2EAF6',     // bg — page background (sky blue)
          2: '#B8DAF0',     // bg-soft — hover states
          3: '#90C3DC',     // border — dividers
        },
        ink: {
          0: '#2a1f14',     // text
          1: '#4a3520',     // text intermediate
          2: '#6e5a45',     // text-muted
          3: '#9b8870',     // text-dim
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
