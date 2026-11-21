// Today's passes of one kind: a filled dot for each pass done, an empty one for each still due.

import { LitElement, css, html, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";

@customElement("tr-passes")
export class TrPasses extends LitElement {
  @property({ type: Number }) done = 0;
  @property({ type: Number }) target = 0;
  @property() icon = "";
  @property() label = "";

  static styles = css`
    :host {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      color: var(--secondary-text-color, #727272);
      font-size: 0.85rem;
    }
    ha-icon {
      --mdc-icon-size: 18px;
    }
    .dots {
      display: inline-flex;
      gap: 4px;
    }
    .dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      border: 2px solid var(--primary-color, #03a9f4);
      box-sizing: border-box;
    }
    .dot.done {
      background: var(--primary-color, #03a9f4);
    }
    .dot.extra {
      border-color: var(--success-color, #43a047);
      background: var(--success-color, #43a047);
    }
    .count {
      font-variant-numeric: tabular-nums;
    }
  `;

  render() {
    if (this.target === 0 && this.done === 0) return nothing;
    const total = Math.max(this.target, this.done);
    const dots = Array.from({ length: total }, (_, i) =>
      i < Math.min(this.done, this.target) ? "done" : i < this.target ? "" : "extra",
    );
    return html`
      ${this.icon ? html`<ha-icon .icon=${this.icon}></ha-icon>` : nothing}
      <span class="dots" role="img" aria-label=${`${this.label}: ${this.done}/${this.target}`}>
        ${dots.map((cls) => html`<span class="dot ${cls}"></span>`)}
      </span>
      <span class="count" aria-hidden="true">${this.done}/${this.target}</span>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tr-passes": TrPasses;
  }
}
