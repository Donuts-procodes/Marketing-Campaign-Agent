import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#fdf8f6",
          100: "#f2e9e4",
          200: "#e8d6ce",
          300: "#d9b6a7",
          400: "#c77f67",
          500: "#C7431F",
          600: "#A9381A",
          700: "#8B2E15",
          800: "#6F2511",
          900: "#4D1A0C",
          950: "#2B0F07",
        },
        // Template surface: warm parchment canvas, terracotta accents, obsidian text.
        canvas: "#FAF6EF",
        ink: { DEFAULT: "#1F1A17", soft: "#6B625A", faint: "#8A8176" },
        line: "#E1D7C8",
        lineLight: "#EFE7DB",
        accent: { DEFAULT: "#C7431F", hover: "#A9381A", tint: "#FDF1EB" },
      },
      fontFamily: {
        sans: ["Manrope", "Plus Jakarta Sans", "system-ui", "sans-serif"],
        display: ["Bricolage Grotesque", "Outfit", "sans-serif"],
        mono: [
          "JetBrains Mono",
          "Fira Code",
          "Cascadia Code",
          "Consolas",
          "monospace",
        ],
      },
      boxShadow: {
        card: "0 1px 2px rgba(25,25,27,0.04), 0 1px 1px rgba(25,25,27,0.03)",
        lift: "0 8px 24px -8px rgba(25,25,27,0.18), 0 2px 6px rgba(25,25,27,0.06)",
      },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "slide-in-right": {
          from: { transform: "translateX(100%)" },
          to: { transform: "translateX(0)" },
        },
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        shimmer: {
          "0%": { backgroundPosition: "-400px 0" },
          "100%": { backgroundPosition: "400px 0" },
        },
      },
      animation: {
        "fade-up": "fade-up 280ms ease-out both",
        "fade-in": "fade-in 180ms ease-out both",
        "slide-in-right": "slide-in-right 260ms cubic-bezier(0.22,1,0.36,1) both",
        shimmer: "shimmer 1.4s linear infinite",
      },
    },
  },
  plugins: [],
};

export default config;
