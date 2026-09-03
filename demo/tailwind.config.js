/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: {
          DEFAULT: "#E4EAE7",
          deep: "#D5DDD9",
          line: "#C2CCC8",
        },
        ink: {
          DEFAULT: "#0E1F22",
          soft: "#3F5559",
          mute: "#6B7F82",
        },
        petrol: {
          DEFAULT: "#0F2A2E",
          2: "#143539",
          3: "#1B4247",
          line: "#245459",
        },
        mist: "#9DB4B0",
        amber: {
          DEFAULT: "#F2B84B",
          deep: "#D99A1E",
        },
        mint: "#7FD1AE",
        coral: "#FF8F70",
        sky: "#8FD3F4",
        lilac: "#C9B8FF",
      },
      fontFamily: {
        display: ['"Bricolage Grotesque"', '"IBM Plex Sans"', "system-ui", "sans-serif"],
        sans: ['"IBM Plex Sans"', "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      keyframes: {
        sweep: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
        rise: {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        sweep: "sweep 1.1s cubic-bezier(.4,0,.2,1) infinite",
        rise: "rise .5s cubic-bezier(.2,.7,.2,1) both",
      },
    },
  },
  plugins: [],
};
