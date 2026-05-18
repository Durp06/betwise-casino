import type { Config } from "tailwindcss";

/**
 * Saloon palette — low-lit, candle-warm, walnut + oxblood + worn felt.
 *
 * Old token names (felt-green / card-red / chip-gold / chipy-dark) remain
 * as aliases pointing at the new palette so existing components inherit
 * the new look without rewrites.
 */
const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // ── Saloon palette ──────────────────────────────────────────────
        saloon: {
          night:     "#15100a",  // base background, near-black walnut
          wood:      "#241812",  // panel surface, dark stained walnut
          oak:       "#3a261c",  // raised panel / divider
          leather:   "#3b1f1d",  // booth banquette / accent surface
          felt:      "#1f3527",  // worn table felt (still green, dimmer/grayer)
          amber:     "#d59140",  // candle / lantern key accent
          brass:     "#8a6a37",  // brass trim, secondary metal
          parchment: "#ede2c2",  // card stock, body text on dark
          ash:       "#9c8a72",  // muted text, secondary
          blood:     "#7e2424",  // hearts/diamonds (deep oxblood, not bright)
          ink:       "#1d1208",  // deepest near-black for card pips on parchment
        },

        // ── Legacy aliases (so existing components inherit the new look) ─
        "felt-green": "#1f3527",  // → saloon.felt
        "card-red":   "#7e2424",  // → saloon.blood
        "chip-gold":  "#d59140",  // → saloon.amber
        "chipy-dark": "#15100a",  // → saloon.night
      },
      fontFamily: {
        sans:    ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["'DM Serif Display'", "Playfair Display", "Georgia", "serif"],
        // For the BetWise logo specifically — wood-type Western feel
        logo:    ["Rye", "'DM Serif Display'", "Georgia", "serif"],
      },
      boxShadow: {
        // Soft inner glow used on panel surfaces to suggest candlelight
        candle: "inset 0 1px 0 0 rgba(255, 220, 160, 0.06), 0 24px 64px -32px rgba(0,0,0,0.7)",
        // Pressed-leather feel for primary buttons
        leather: "inset 0 1px 0 0 rgba(255,220,160,0.18), inset 0 -2px 0 0 rgba(0,0,0,0.35), 0 2px 0 0 rgba(0,0,0,0.25)",
        // Brass trim ring used on important interactive surfaces
        brass: "0 0 0 1px rgba(138,106,55,0.6), 0 8px 24px -8px rgba(0,0,0,0.6)",
        // Card on table — settled, with shadow toward the bottom
        card: "0 6px 12px -6px rgba(0,0,0,0.6), 0 1px 0 0 rgba(255,255,255,0.04)",
      },
      backgroundImage: {
        // CSS-only noise + vignette layers for the body — no asset files needed
        "saloon-vignette":
          "radial-gradient(120% 90% at 50% 30%, rgba(213,145,64,0.06) 0%, transparent 45%), " +
          "radial-gradient(120% 100% at 50% 100%, rgba(0,0,0,0.55) 50%, transparent 100%)",
        "saloon-grain":
          "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3CfeColorMatrix values='0 0 0 0 0.10 0 0 0 0 0.07 0 0 0 0 0.04 0 0 0 0.45 0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")",
        "saloon-parchment-grain":
          "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='1.2' numOctaves='2' stitchTiles='stitch'/%3E%3CfeColorMatrix values='0 0 0 0 0.20 0 0 0 0 0.15 0 0 0 0 0.07 0 0 0 0.10 0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")",
      },
    },
  },
  plugins: [],
};

export default config;
