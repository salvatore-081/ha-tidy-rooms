// Callbacks that make ha-form speak the panel's language.

import type { Localize } from "./localize";
import type { FormField } from "./types";

export interface FormCallbacks {
  computeLabel: (field: FormField) => string;
  computeHelper: (field: FormField) => string | undefined;
  computeError: (error: string, field?: FormField) => string;
  localizeValue: (key: string) => string;
}

export const formCallbacks = (t: Localize): FormCallbacks => ({
  computeLabel: (field) => t(`field.${field.name}`),
  computeHelper: (field) => {
    const key = `help.${field.name}`;
    const text = t(key);
    return text === key ? undefined : text;
  },
  // ha-form passes our error codes (area_already_configured, invalid, ...).
  computeError: (error) => {
    const key = `error.${error}`;
    const text = t(key);
    return text === key ? error : text;
  },
  // Select options with a translation key: "weekday.options.mon".
  localizeValue: (key) => {
    const text = t(`selector.${key}`);
    return text === `selector.${key}` ? key.split(".").pop() || key : text;
  },
});

/** Field errors of a save, with "base" shown above the form. */
export const splitErrors = (errors: Record<string, string> | undefined) => {
  const { base, ...fields } = errors ?? {};
  return { base, fields };
};
