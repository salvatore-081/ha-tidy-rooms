// Entry point of the dashboard card (loaded on every page of the frontend).
import "./card/tidy-rooms-card";
import "./card/tidy-rooms-card-editor";
import { localize } from "./localize";

interface CustomCardEntry {
  type: string;
  name: string;
  description: string;
  preview?: boolean;
  documentationURL?: string;
}

const w = window as unknown as { customCards?: CustomCardEntry[] };
w.customCards = w.customCards || [];
if (!w.customCards.some((c) => c.type === "tidy-rooms-card")) {
  const language = document.documentElement.lang || navigator.language;
  w.customCards.push({
    type: "tidy-rooms-card",
    name: localize("card.name", language),
    description: localize("card.description", language),
    preview: true,
    documentationURL: "https://github.com/salvatore-081/ha-tidy-rooms",
  });
}
