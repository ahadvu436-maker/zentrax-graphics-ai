/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Semantic tokens — map to the CSS variables defined in globals.css
        background: "rgb(var(--background) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        foreground: "rgb(var(--foreground) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        accent: {
          DEFAULT: "rgb(var(--accent) / <alpha-value>)",
          foreground: "rgb(var(--accent-foreground) / <alpha-value>)",
        },
        danger: "rgb(var(--danger) / <alpha-value>)",

        // Zentrax brand palette (static values, independent of theme vars)
        zentrax: {
          black: "#0a0a0a",
          charcoal: "#171717",
          gold: {
            50: "#fffbeb",
            100: "#fef3c7",
            300: "#fcd34d",
            500: "#f59e0b",
            600: "#d97706",
            700: "#b45309",
          },
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      borderRadius: {
        xl: "0.875rem",
        "2xl": "1.25rem",
      },
      boxShadow: {
        glow: "0 0 24px 0 rgb(245 158 11 / 0.25)", // amber glow for accent elements
      },
      keyframes: {
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.25s ease-out both",
        shimmer: "shimmer 2s linear infinite",
      },
      backgroundImage: {
        "shimmer-gradient":
          "linear-gradient(110deg, rgb(38 38 38) 8%, rgb(64 64 64) 18%, rgb(38 38 38) 33%)",
      },
    },
  },
  plugins: [],
};