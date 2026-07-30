import {nextui} from '@nextui-org/theme'

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './utils/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './node_modules/@nextui-org/theme/dist/**/*.{js,ts,jsx,tsx}'
  ],
  safelist: [
    {
      pattern: /(bg|text)-(red|green|blue|gray)-\d+/,
    },
  ],
  theme: {
    extend: {
      colors: {
        ink: {
          DEFAULT: "var(--ink)",
          muted: "var(--ink-muted)",
        },
        surface: {
          DEFAULT: "var(--surface)",
          muted: "var(--surface-muted)",
          solid: "var(--surface-solid)",
        },
        border: {
          DEFAULT: "var(--border)",
          strong: "var(--border-strong)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          subtle: "var(--accent-subtle)",
          hover: "var(--accent-hover)",
        },
      },
      borderRadius: {
        'app-sm': "var(--radius-sm)",
        'app-md': "var(--radius-md)",
        'app-lg': "var(--radius-lg)",
      },
      boxShadow: {
        card: "var(--shadow-card)",
        soft: "var(--shadow-soft)",
      },
      fontFamily: {
        sans: ["var(--font-sans)"],
        mono: ["var(--font-mono)"],
      },
      screens: {
        'xs': '400px',
        'sm': '540px',
      },
      keyframes: {
        'fade-in': {
          '0%': { opacity: 0 },
          '100%': { opacity: 1 },
        },
        'fade-out': {
          '0%': { opacity: 1 },
          '100%': { opacity: 0 },
        },
        'fade-in-up': {
          '0%': { opacity: 0, transform: 'translateY(-10px)' },
          '100%': { opacity: 1, transform: 'translateY(0)' },
        },
        'pop': {
          '0%': { transform: 'scale(1)' },
          '50%': { transform: 'scale(1.05)' },
          '100%': { transform: 'scale(1)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.3s ease-in-out',
        'fade-out': 'fade-out 0.3s ease-out forwards',
        'fade-in-up': 'fade-in-up 0.3s ease-in-out',
        'pop': 'pop 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
      },
    },
  },
  future: {
    hoverOnlyWhenSupported: true,
  },
  darkMode: "class",
  plugins: [
    nextui({
      themes: {
        light: {
          colors: {
            background: "#eef6ff",
            foreground: "#1e293b",
            content1: "#ffffff",
            content2: "#f1f5f9",
            content3: "#e2e8f0",
            content4: "#cbd5e1",
            default: {
              50: "#f8fafc",
              100: "#f1f5f9",
              200: "#e2e8f0",
              300: "#cbd5e1",
              400: "#94a3b8",
              500: "#64748b",
              600: "#475569",
              700: "#334155",
              800: "#1e293b",
              900: "#0f172a",
              DEFAULT: "#e2e8f0",
              foreground: "#1e293b",
            },
            primary: {
              50: "#eff6ff",
              100: "#dbeafe",
              200: "#bfdbfe",
              300: "#93c5fd",
              400: "#60a5fa",
              500: "#3b82f6",
              600: "#2c85ff",
              700: "#1d6fe8",
              800: "#1e40af",
              900: "#1e3a8a",
              DEFAULT: "#2c85ff",
              foreground: "#ffffff",
            },
            focus: "#2c85ff",
          },
        },
        dark: {
          colors: {
            background: "#0b1220",
            foreground: "#f1f5f9",
            content1: "#1e293b",
            content2: "#334155",
            content3: "#475569",
            content4: "#64748b",
            default: {
              50: "#0f172a",
              100: "#1e293b",
              200: "#334155",
              300: "#475569",
              400: "#64748b",
              500: "#94a3b8",
              600: "#cbd5e1",
              700: "#e2e8f0",
              800: "#f1f5f9",
              900: "#f8fafc",
              DEFAULT: "#334155",
              foreground: "#f1f5f9",
            },
            primary: {
              50: "#0f172a",
              100: "#1e3a8a",
              200: "#1e40af",
              300: "#1d6fe8",
              400: "#3b82f6",
              500: "#60a5fa",
              600: "#93c5fd",
              700: "#bfdbfe",
              800: "#dbeafe",
              900: "#eff6ff",
              DEFAULT: "#60a5fa",
              foreground: "#0f172a",
            },
            focus: "#60a5fa",
          },
        },
      },
    }),
  ],
}
