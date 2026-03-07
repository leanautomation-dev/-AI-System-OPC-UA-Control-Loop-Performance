/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        industrial: {
          50: '#f0f7ff',
          100: '#e0effe',
          200: '#bae0fd',
          300: '#7dc9fb',
          400: '#38acf7',
          500: '#0e91e8',
          600: '#0273c6',
          700: '#025ca0',
          800: '#064e84',
          900: '#0b426d',
          950: '#072a48',
        },
        alarm: {
          critical: '#dc2626',
          high: '#ea580c',
          medium: '#ca8a04',
          low: '#16a34a',
        },
        grade: {
          good: '#16a34a',
          acceptable: '#ca8a04',
          poor: '#ea580c',
          bad: '#dc2626',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
};
