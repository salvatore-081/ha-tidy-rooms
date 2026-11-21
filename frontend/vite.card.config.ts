import { resolve } from "node:path";
import { defineConfig, type Plugin } from "vite";

// The card is loaded on every page of the frontend: ship only its strings.
// The locale filter is adapted from RoomMind (https://github.com/snazzybean/roommind,
// MIT, Copyright (c) 2026 SnazzyBean).
const CARD_KEY_PREFIXES = [
  "card.",
  "status.",
  "kind.",
  "wait.",
  "outlook.",
  "robot.",
  "time.",
  "job.",
];

function cardLocales(): Plugin {
  return {
    name: "tidy-rooms-card-locales",
    enforce: "pre",
    transform(code, id) {
      if (!/[\\/]locales[\\/][a-z]+\.json$/.test(id)) return null;
      const all = JSON.parse(code) as Record<string, string>;
      const kept = Object.fromEntries(
        Object.entries(all).filter(([key]) => CARD_KEY_PREFIXES.some((p) => key.startsWith(p))),
      );
      return { code: JSON.stringify(kept), map: null };
    },
  };
}

export default defineConfig({
  plugins: [cardLocales()],
  build: {
    lib: {
      entry: resolve(import.meta.dirname, "src/card.ts"),
      name: "TidyRoomsCard",
      formats: ["iife"],
      fileName: () => "tidy-rooms-card.js",
    },
    outDir: "../custom_components/tidy_rooms/frontend",
    emptyOutDir: false,
    target: "es2022",
    reportCompressedSize: false,
  },
});
