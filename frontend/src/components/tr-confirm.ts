// A confirmation dialog. Plain fixed overlay (not a top-layer <dialog>), so it
// stays below the frontend's own popups.

import { element } from "../define";
import { LitElement, css, html, nothing } from "lit";
import { property, query, state } from "lit/decorators.js";
import { shared, tokens } from "../styles";

export interface Choice {
  value: string;
  label: string;
  /** A second line under the label. */
  hint?: string;
}

export interface ConfirmOptions {
  title: string;
  text: string;
  confirm: string;
  cancel: string;
  destructive?: boolean;
  /** Options to pick one from (radio buttons), with the one selected first. */
  choices?: Choice[];
  selected?: string;
}

@element("tr-confirm")
export class TrConfirm extends LitElement {
  @property({ attribute: false }) options!: ConfirmOptions;
  @query(".confirm") private _confirmButton!: HTMLButtonElement;
  @state() private _value?: string;
  resolve?: (ok: boolean, value?: string) => void;

  static styles = [
    tokens,
    shared,
    css`
      .backdrop {
        position: fixed;
        inset: 0;
        z-index: 7;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 16px;
        background: rgba(0, 0, 0, 0.45);
      }
      .dialog {
        width: min(440px, 100%);
        padding: 24px;
        box-sizing: border-box;
      }
      h2 {
        margin: 0 0 12px;
        font-size: 1.25rem;
        font-weight: 500;
      }
      p {
        margin: 0 0 24px;
        color: var(--tr-muted);
        line-height: 1.5;
      }
      .choices {
        display: grid;
        gap: 4px;
        margin: -12px 0 20px;
        border: 0;
        padding: 0;
      }
      .choices label {
        display: flex;
        gap: 10px;
        align-items: flex-start;
        padding: 8px;
        border-radius: 8px;
        cursor: pointer;
      }
      .choices label:hover {
        background: color-mix(in srgb, var(--tr-primary) 8%, transparent);
      }
      .choices input {
        margin: 3px 0 0;
        accent-color: var(--tr-primary);
      }
      .choices .hint {
        display: block;
        color: var(--tr-muted);
        font-size: 0.85rem;
      }
      .actions {
        display: flex;
        justify-content: flex-end;
        gap: 8px;
        flex-wrap: wrap;
      }
    `,
  ];

  firstUpdated() {
    this._confirmButton.focus();
  }

  willUpdate() {
    if (this._value === undefined && this.options.choices?.length)
      this._value = this.options.selected ?? this.options.choices[0].value;
  }

  render() {
    const o = this.options;
    return html`
      <div class="backdrop" @click=${this._backdrop} @keydown=${this._keydown}>
        <div class="dialog card" role="alertdialog" aria-modal="true" aria-labelledby="t">
          <h2 id="t">${o.title}</h2>
          <p>${o.text}</p>
          ${
            o.choices?.length
              ? html`<fieldset class="choices">
                  <legend class="sr-only">${o.title}</legend>
                  ${o.choices.map(
                    (c) =>
                      html`<label>
                        <input
                          type="radio"
                          name="choice"
                          .value=${c.value}
                          .checked=${c.value === this._value}
                          @change=${() => (this._value = c.value)}
                        />
                        <span
                          >${c.label}${
                            c.hint ? html`<span class="hint">${c.hint}</span>` : nothing
                          }</span
                        >
                      </label>`,
                  )}
                </fieldset>`
              : nothing
          }
          <div class="actions">
            <button class="btn" @click=${() => this._close(false)}>${o.cancel}</button>
            <button
              class="btn filled confirm ${o.destructive ? "danger" : ""}"
              @click=${() => this._close(true)}
            >
              ${o.confirm}
            </button>
          </div>
        </div>
      </div>
    `;
  }

  private _backdrop(ev: Event) {
    if (ev.target === ev.currentTarget) this._close(false);
  }

  private _keydown(ev: KeyboardEvent) {
    if (ev.key === "Escape") this._close(false);
  }

  private _close(ok: boolean) {
    this.resolve?.(ok, ok ? this._value : undefined);
    this.remove();
  }
}

/** Show a confirmation inside `host` (a shadow root keeps the theme variables). */
export const confirmDialog = (host: HTMLElement | ShadowRoot, options: ConfirmOptions) =>
  new Promise<boolean>((resolve) => {
    const el = document.createElement("tr-confirm");
    el.options = options;
    el.resolve = resolve;
    host.appendChild(el);
  });

/** Ask to pick one of `options.choices`; resolves to its value, or null if cancelled. */
export const choiceDialog = (host: HTMLElement | ShadowRoot, options: ConfirmOptions) =>
  new Promise<string | null>((resolve) => {
    const el = document.createElement("tr-confirm");
    el.options = options;
    el.resolve = (ok, value) => resolve(ok ? (value ?? null) : null);
    host.appendChild(el);
  });

declare global {
  interface HTMLElementTagNameMap {
    "tr-confirm": TrConfirm;
  }
}
