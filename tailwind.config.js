/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/templates/**/*.html",
    "./app/static/js/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        veil: {
          50: "#eef4ff",
          500: "#4f6ef7",
          600: "#3b55e0",
          700: "#2f44b8",
          900: "#1b2560",
        },
      },
    },
  },
  plugins: [],
};
