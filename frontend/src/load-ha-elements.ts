// Home Assistant loads its own elements lazily. A custom panel opened directly
// (a bookmark, a reload) may find <ha-form> undefined: these helpers load it
// the way other custom panels do, through the modules of built-in panels.

/* eslint-disable @typescript-eslint/no-explicit-any -- frontend internals are untyped */

const waitFor = (tag: string, ms: number): Promise<boolean> =>
  Promise.race([
    customElements.whenDefined(tag).then(() => true),
    new Promise<boolean>((resolve) => setTimeout(() => resolve(false), ms)),
  ]);

/** Import a built-in panel's module without showing it. */
const loadPanelModule = async (componentName: string): Promise<void> => {
  if (!(await waitFor("partial-panel-resolver", 5000))) return;
  const resolver = document.createElement("partial-panel-resolver") as any;
  resolver.hass = { panels: [{ url_path: "tmp", component_name: componentName }] };
  resolver._updateRoutes();
  await resolver.routerOptions.routes.tmp.load();
};

let loading: Promise<boolean> | undefined;

/** Resolves to true once <ha-form> is defined (false after trying everything). */
export const loadHaForm = (): Promise<boolean> => {
  loading ??= (async () => {
    if (customElements.get("ha-form")) return true;
    // 1. The automation editor uses ha-form everywhere.
    try {
      await loadPanelModule("config");
      if (await waitFor("ha-panel-config", 5000)) {
        const config = document.createElement("ha-panel-config") as any;
        await config.routerOptions.routes.automation.load();
      }
    } catch {
      // try the next way
    }
    if (customElements.get("ha-form")) return true;
    // 2. Card editors use ha-form; loadCardHelpers exists after a dashboard was shown.
    try {
      const helpers = await (window as any).loadCardHelpers?.();
      if (helpers) {
        const card = await helpers.createCardElement({ type: "tile", entity: "sun.sun" });
        await card.constructor.getConfigElement?.();
      }
    } catch {
      // give up below
    }
    return waitFor("ha-form", 10_000);
  })();
  return loading;
};
