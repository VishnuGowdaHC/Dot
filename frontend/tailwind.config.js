/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./dist/**/*.{html,js}",
    "./index.html",
    "./src/**/*.{html,js,css}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      colors: {
        dot: {
          bg: '#121626',
          card: '#161c32',
          shelf: '#1e2646',
          purple: '#a78bfa',
          indigo: '#818cf8',
          pink: '#f472b6',
          blue: '#60a5fa',
        }
      }
    },
  },
  plugins: [],
}

