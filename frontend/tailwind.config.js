/** @type {import('tailwindcss').Config} */
// NOTE: Tailwind v4 uses @tailwindcss/postcss and largely config-free.
// This file is kept for the fontFamily extension and content paths.
// The `require("tailwindcss-animate")` plugin is NOT compatible with v4 —
// animations are handled via globals.css @keyframes instead.
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
    "./pages/**/*.{js,ts,jsx,tsx}",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        // These map to the CSS variables set in globals.css
        sans:    ["'Instrument Sans'", "system-ui", "sans-serif"],
        mono:    ["'Martian Mono'", "ui-monospace", "monospace"],
        display: ["'Bebas Neue'", "'Arial Black'", "sans-serif"],
        serif:   ["'DM Serif Display'", "Georgia", "serif"],
      },
    },
  },
  // tailwindcss-animate is NOT compatible with Tailwind v4 — removed
  plugins: [],
};
