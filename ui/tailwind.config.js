/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#161b27",
        panel: "#1f2637",
        panel2: "#262e42",
        border: "#353e57",
        ink: "#ecf0f8",
        subt: "#9aa3b8",
        // Status palette for the little squares.
        s_new: "#3b4150",
        s_needs_delve: "#d4a45c",
        s_low: "#4a4e5c",
        s_fp: "#2b2f3c",
        s_delved: "#9a6ad1",
        s_draft: "#5884d9",
        s_sent: "#4fae7a",
        s_closed: "#3a3e4a",
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
