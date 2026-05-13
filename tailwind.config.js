/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./index.html', './src/**/*.{vue,ts}'],
  theme: {
    extend: {
      colors: {
        kiwi: {
          50: '#f8fbf1',
          100: '#edf6db',
          200: '#d9ebb3',
          400: '#9bc447',
          600: '#6f961f',
          800: '#405a17',
        },
      },
      boxShadow: {
        kiwi: '0 16px 40px rgba(111, 150, 31, 0.14)',
      },
    },
  },
  plugins: [],
}
