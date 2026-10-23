/** @type {import('tailwindcss').Config} */
// Ported exactly from the inline tailwind.config that index.html used to
// pass to the cdn.tailwindcss.com Play script (removed in this change):
// the only theme extension was the sans font stack below.
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Inter",
          "\"Noto Sans SC\"",
          "\"PingFang SC\"",
          "\"Hiragino Sans GB\"",
          "\"Microsoft YaHei\"",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "\"Segoe UI\"",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};
