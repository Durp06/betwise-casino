import type { Config } from "tailwindcss";

/**
 * Cuphead / rubber-hose / vintage-Vegas palette.
 *
 * Bold saturated primaries (not pastels, not neons), cream paper for
 * surfaces, deep ink for outlines. Every interactive element should be
 * outlined with #1A0A00.
 */
const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        felt: {
          dark:  "#0D3B1F",   // table base
          mid:   "#145A32",   // felt mid
          light: "#1E8449",   // felt highlight
        },
        cream:  "#F5F0E8",    // off-white paper, all text/card bg
        ink:    "#1A0A00",    // near-black, outlines + primary text
        gold: {
          bright: "#F4D03F",
          mid:    "#D4AC0D",
          dark:   "#9A7D0A",
        },
        chip: {
          red:    "#C0392B",
          blue:   "#1A5276",
          green:  "#1E8449",
          black:  "#1A1A1A",
          white:  "#F5F0E8",
          purple: "#6C3483",
        },
        action: {
          hit:    "#E74C3C",
          stand:  "#27AE60",
          double: "#2980B9",
          split:  "#8E44AD",
        },

        // Legacy aliases — point old tokens at the new palette so any
        // un-rewritten component still renders something sensible.
        "felt-green": "#145A32",  // → felt.mid
        "card-red":   "#C0392B",  // → chip.red
        "chip-gold":  "#D4AC0D",  // → gold.mid
        "chipy-dark": "#1A0A00",  // → ink
        saloon: {
          // Just enough to stop classes from breaking; cosmetics ignored.
          night:     "#1A0A00",
          wood:      "#1A0A00",
          oak:       "#241812",
          leather:   "#C0392B",
          felt:      "#145A32",
          amber:     "#D4AC0D",
          brass:     "#9A7D0A",
          parchment: "#F5F0E8",
          ash:       "#9A9A9A",
          blood:     "#C0392B",
          ink:       "#1A0A00",
        },
      },
      fontFamily: {
        display: ["'Luckiest Guy'", "Impact", "system-ui", "sans-serif"],
        ui:      ["'Lilita One'", "ui-sans-serif", "sans-serif"],
        body:    ["'Fredoka One'", "ui-sans-serif", "sans-serif"],
        flavor:  ["'Special Elite'", "Courier", "monospace"],
        // Default sans falls back to Fredoka for readable copy
        sans:    ["'Fredoka One'", "ui-sans-serif", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
