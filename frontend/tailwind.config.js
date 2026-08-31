module.exports = {
  content: ["./index.html", "./script.ts"],
  corePlugins: { preflight: false },  // don't clobber our existing hand-built CSS
  theme: {
    extend: {
      colors: {
        abyss: "#081C2A",
        panel: "#0E2A38",
        panel2: "#0C2531",
        line: "#17394A",
        cyan: "#4FE7C1",
        coral: "#FF8A65",
        violet: "#9C8CF0",
        amber: "#F2C078",
        foam: "#EAF3EF",
        mist: "#AFC4C2",
        dim: "#72908D",
      },
      fontFamily: {
        serif: ["Fraunces", "Georgia", "serif"],
        mono: ["IBM Plex Mono", "monospace"],
      },
    },
  },
  plugins: [],
};
