// Strings of the panel and of the card, in the languages of the integration.

import de from "./locales/de.json";
import en from "./locales/en.json";
import es from "./locales/es.json";
import fr from "./locales/fr.json";
import it from "./locales/it.json";

type Strings = Record<string, string>;

export const LANGUAGES: Record<string, Strings> = { en, it, de, es, fr };

/** The supported language for a Home Assistant language code (it, en-GB, pt-BR, ...). */
export const pickLanguage = (language: string | undefined): string => {
  const base = (language || "en").toLowerCase().split(/[-_]/)[0];
  return base in LANGUAGES ? base : "en";
};

/**
 * The string for `key` in `language`, falling back to English, then to the key.
 * `{name}` placeholders are replaced with `params[name]`.
 */
export const localize = (
  key: string,
  language: string | undefined,
  params: Record<string, string | number> = {},
): string => {
  const strings = LANGUAGES[pickLanguage(language)];
  let text = strings[key] ?? en[key as keyof typeof en] ?? key;
  for (const [name, value] of Object.entries(params)) {
    text = text.replaceAll(`{${name}}`, String(value));
  }
  return text;
};

export type Localize = (key: string, params?: Record<string, string | number>) => string;

export const localizer =
  (language: string | undefined): Localize =>
  (key, params) =>
    localize(key, language, params);
