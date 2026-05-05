import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        orbitron: ["var(--font-orbitron)", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
      },
      colors: {
        neon: {
          cyan: "#00f5ff",
          pink: "#ff00aa",
          green: "#39ff14",
          orange: "#ff6b00",
          yellow: "#ffd700",
        },
      },
      animation: {
        "pulse-cyan": "pulse-cyan 2s ease-in-out infinite",
        "pulse-green": "pulse-green 2s ease-in-out infinite",
        flicker: "flicker 5s ease-in-out infinite",
        "slide-in-right": "slide-in-right 0.3s ease-out forwards",
        "slide-in-up": "slide-in-up 0.4s ease-out forwards",
        "fade-in": "fade-in 0.3s ease-out forwards",
        "scan-line": "scan-line 4s linear infinite",
      },
      backdropBlur: {
        xs: "2px",
      },
      boxShadow: {
        "neon-cyan": "0 0 10px #00f5ff, 0 0 20px rgba(0,245,255,0.4), 0 0 40px rgba(0,245,255,0.2)",
        "neon-pink": "0 0 10px #ff00aa, 0 0 20px rgba(255,0,170,0.4)",
        "neon-green": "0 0 10px #39ff14, 0 0 20px rgba(57,255,20,0.4)",
      },
    },
  },
  plugins: [],
};

export default config;
