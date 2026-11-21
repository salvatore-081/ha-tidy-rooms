import { describe, expect, it } from "vitest";
import { LANGUAGES, localize, pickLanguage } from "../src/localize";

const placeholders = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe("locales", () => {
  const en = LANGUAGES.en;
  for (const [lang, strings] of Object.entries(LANGUAGES)) {
    it(`${lang} has every key of en, with the same placeholders`, () => {
      expect(Object.keys(strings).sort()).toEqual(Object.keys(en).sort());
      for (const [key, text] of Object.entries(en)) {
        expect(placeholders(strings[key]), `${lang} ${key}`).toEqual(placeholders(text));
      }
    });
  }

  it("picks the base language and falls back to English", () => {
    expect(pickLanguage("it")).toBe("it");
    expect(pickLanguage("de-CH")).toBe("de");
    expect(pickLanguage("pt-BR")).toBe("en");
    expect(pickLanguage(undefined)).toBe("en");
  });

  it("fills placeholders and falls back to the key", () => {
    expect(localize("time.minutes", "it", { n: 5 })).toBe("5 min");
    expect(localize("no.such.key", "it")).toBe("no.such.key");
  });
});
