// Today's passes of a room: a dot each, filled when done, crossed when skipped.

import { element } from "../define";
import { LitElement, css, html, nothing } from "lit";
import { property } from "lit/decorators.js";
import { type FormatContext, formatTime, passWindow } from "../format";
import type { PassSnapshot } from "../types";

/** The text of one pass for tooltips and screen readers. */
export const passDescription = (p: PassSnapshot, ctx: FormatContext): string => {
  const { t } = ctx;
  const status =
    p.status === "done" && p.done_at
      ? t("pass_status.done_at", { time: formatTime(p.done_at, ctx) })
      : t(`pass_status.${p.status}`);
  return `${ctx.mode(p.work_mode)}, ${passWindow(p, ctx)}: ${status}`;
};

@element("tr-passes")
export class TrPasses extends LitElement {
  @property({ attribute: false }) passes: PassSnapshot[] = [];
  @property({ attribute: false }) ctx!: FormatContext;

  static styles = css`
    :host {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      color: var(--secondary-text-color, #727272);
      font-size: 0.85rem;
    }
    .dots {
      display: inline-flex;
      gap: 4px;
    }
    .dot {
      position: relative;
      width: 10px;
      height: 10px;
      border-radius: 50%;
      border: 2px solid var(--primary-color, #03a9f4);
      box-sizing: border-box;
    }
    .dot.done {
      background: var(--primary-color, #03a9f4);
    }
    .dot.active {
      background: color-mix(in srgb, var(--primary-color, #03a9f4) 45%, transparent);
    }
    .dot.skipped {
      border-color: var(--disabled-text-color, #bdbdbd);
    }
    .dot.skipped::after {
      content: "";
      position: absolute;
      left: -2px;
      right: -2px;
      top: 2px;
      border-top: 2px solid var(--disabled-text-color, #bdbdbd);
      transform: rotate(-45deg);
    }
    .count {
      font-variant-numeric: tabular-nums;
    }
  `;

  render() {
    const today = this.passes.filter((p) => p.status !== "not_today");
    if (!today.length) return nothing;
    const done = today.filter((p) => p.status === "done").length;
    const label = this.ctx.t("pass.count", { done, total: today.length });
    return html`
      <span class="dots" role="img" aria-label=${label}>
        ${today.map(
          (p) => html`<span class="dot ${p.status}" title=${passDescription(p, this.ctx)}></span>`,
        )}
      </span>
      <span class="count" aria-hidden="true">${done}/${today.length}</span>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tr-passes": TrPasses;
  }
}
