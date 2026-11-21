// The panel and the card are separate bundles that share components: the
// first one loaded defines them, the second must not define them again.

export const element =
  (name: string) =>
  (cls: CustomElementConstructor): void => {
    if (!customElements.get(name)) customElements.define(name, cls);
  };
