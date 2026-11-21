// A confirmation dialog. Plain fixed overlay (not a top-layer <dialog>), so it
// stays below the frontend's own popups.

import { element } from "../define";
import { LitElement, css, html } from "lit";
import { property, query } from "lit/decorators.js";
import { shared, tokens } from "../styles";

export interface ConfirmOptions {
  title: string;
  text: string;
  confirm: string;
  cancel: string;
  destructive?: boolean;
}

@element("tr-confirm")
export class TrConfirm extends LitElement {
  @property({ attribute: false }) options!: ConfirmOptions;
  @query(".confirm") private _confirmButton!: HTMLButtonElement;
  resolve?: (ok: boolean) => void;

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

  render() {
    const o = this.options;
    return html`
      <div class="backdrop" @click=${this._backdrop} @keydown=${this._keydown}>
        <div class="dialog card" role="alertdialog" aria-modal="true" aria-labelledby="t">
          <h2 id="t">${o.title}</h2>
          <p>${o.text}</p>
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
    this.resolve?.(ok);
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

declare global {
  interface HTMLElementTagNameMap {
    "tr-confirm": TrConfirm;
  }
}
