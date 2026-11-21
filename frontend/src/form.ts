// Callbacks that make ha-form speak the panel's language.

import type { Localize } from "./localize";
import type { FormField, HomeAssistant } from "./types";

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

const FAN_FIELDS = ["fan_speed", "normal_fan_speed", "quiet_fan_speed"];
const MODE_FIELDS = ["work_mode"];

/** The robot's own name of a fan speed ("max_plus" → "Max+"), as Home Assistant shows it. */
export const fanSpeedLabel = (hass: HomeAssistant, vacuum: string, value: string): string => {
  const state = hass.states[vacuum];
  try {
    return (state && hass.formatEntityAttributeValue?.(state, "fan_speed", value)) || value;
  } catch {
    return value;
  }
};

/** The translated name of a work mode ("mop_after_vacuum" → "Aspirazione poi lavaggio"). */
export const workModeLabel = (
  hass: HomeAssistant,
  workModeEntity: string | null | undefined,
  value: string,
): string => {
  const state = workModeEntity ? hass.states[workModeEntity] : undefined;
  try {
    return (state && hass.formatEntityState?.(state, value)) || value;
  } catch {
    return value;
  }
};

/**
 * Give the fan speed and work mode menus the names Home Assistant shows
 * for them, keeping the raw value when there is no translation.
 */
export const labelRobotOptions = (
  schema: FormField[],
  hass: HomeAssistant,
  vacuum: string,
  workModeEntity: string | null | undefined,
): FormField[] =>
  schema.map((field) => {
    const select = (field.selector as { select?: { options?: unknown[] } } | undefined)?.select;
    if (!select?.options) return field;
    const label = FAN_FIELDS.includes(field.name)
      ? (v: string) => fanSpeedLabel(hass, vacuum, v)
      : MODE_FIELDS.includes(field.name)
        ? (v: string) => workModeLabel(hass, workModeEntity, v)
        : undefined;
    if (!label) return field;
    const options = select.options.map((o) => {
      const value = typeof o === "string" ? o : (o as { value: string }).value;
      const text = label(value);
      return { value, label: text === value ? value : `${text} (${value})` };
    });
    return { ...field, selector: { select: { ...select, options } } };
  });
