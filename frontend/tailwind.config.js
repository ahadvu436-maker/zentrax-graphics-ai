/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        zentrax: {
          black: "#0a0a0a",
          charcoal: "#171717",
          50: "#fffbeb",
          100: "#fef3c7",
          300: "#fde047",
          500: "#f59e0b",
          600: "#d97706",
          700: "#b45309",
        },
      },
    },
  },
  plugins: [],
};
