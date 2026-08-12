/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["PingFang SC", "Microsoft YaHei", "system-ui", "sans-serif"],
      },
      colors: {
        primary: { DEFAULT: "#1677FF", dark: "#0958D9", light: "#4096FF" },
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
