// Navigation inside the frontend, and toasts.

export const BASE = "/tidy-rooms";

/** Change the URL the way the frontend does, so it updates `route`. */
export const navigate = (path: string, replace = false) => {
  if (replace) history.replaceState(null, "", path);
  else history.pushState(null, "", path);
  window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace } }));
};

/** A path of the panel, keeping the selected robot (?entry=). */
export const panelPath = (path = "") => `${BASE}${path}${location.search}`;

/** Show a toast of the frontend. */
export const notify = (el: HTMLElement, message: string) =>
  el.dispatchEvent(
    new CustomEvent("hass-notification", { detail: { message }, bubbles: true, composed: true }),
  );
