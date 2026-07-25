import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        sunshine: {
          50: "#fffbea",
          100: "#fff3c4",
          400: "#f5c518",
          500: "#e0a800",
          600: "#b58200",
        },
        ledger: {
          900: "#0f172a",
          700: "#334155",
        },
      },
    },
  },
  plugins: [],
};

export default config;
