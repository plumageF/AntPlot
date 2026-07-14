/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        graphite: {
          950: "#0b1120",
          900: "#111827",
          850: "#172033"
        }
      },
      boxShadow: {
        soft: "0 18px 45px rgba(15, 23, 42, 0.12)",
        glow: "0 0 0 4px rgba(99, 102, 241, 0.16)"
      }
    }
  },
  plugins: []
};
