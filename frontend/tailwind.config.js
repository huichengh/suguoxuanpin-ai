/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f0f9f4',
          100: '#dcf0e5',
          200: '#b8e1cb',
          300: '#8bcbaa',
          400: '#57ad84',
          500: '#338f68',
          600: '#257354',
          700: '#1f5c45',
          800: '#1c4a39',
          900: '#183d31',
        },
        alert: {
          orange: '#e8833a',
          red: '#d94a4a',
        },
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', '"PingFang SC"',
               '"Hiragino Sans GB"', '"Microsoft YaHei"', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
