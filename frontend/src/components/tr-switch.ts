// A small accessible switch, independent from the frontend's own (which changes often).

import { element } from "../define";
import { LitElement, css, html } from "lit";
import { property } from "lit/decorators.js";

@element("tr-switch")
export class TrSwitch extends LitElement {
  @property({ type: Boolean, reflect: true }) checked = false;
  @property({ type: Boolean, reflect: true }) disabled = false;
  @property() label = "";

  static styles = css`
    :host {
      display: inline-flex;
      flex: none;
    }
    button {
      position: relative;
      width: 40px;
      height: 24px;
      border-radius: 12px;
      border: 2px solid var(--secondary-text-color, #727272);
      background: transparent;
      padding: 0;
      cursor: pointer;
      transition:
        background 0.15s,
        border-color 0.15s;
    }
    button::after {
      content: "";
      position: absolute;
      top: 3px;
      left: 3px;
      width: 14px;
      height: 14px;
      border-radius: 50%;
      background: var(--secondary-text-color, #727272);
      transition:
        transform 0.15s,
        background 0.15s;
    }
    :host([checked]) button {
      background: var(--primary-color, #03a9f4);
      border-color: var(--primary-color, #03a9f4);
    }
    :host([checked]) button::after {
      transform: translateX(16px);
      background: var(--text-primary-color, #fff);
    }
    :host([disabled]) button {
      opacity: 0.5;
      cursor: default;
    }
    button:focus-visible {
      outline: 2px solid var(--primary-color, #03a9f4);
      outline-offset: 2px;
    }
  `;

  render() {
    return html`<button
      role="switch"
      aria-checked=${this.checked ? "true" : "false"}
      aria-label=${this.label}
      title=${this.label}
      ?disabled=${this.disabled}
      @click=${this._toggle}
    ></button>`;
  }

  private _toggle(ev: Event) {
    ev.stopPropagation();
    if (this.disabled) return;
    this.checked = !this.checked;
    this.dispatchEvent(
      new CustomEvent("change", {
        detail: { checked: this.checked },
        bubbles: true,
        composed: true,
      }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tr-switch": TrSwitch;
  }
}
