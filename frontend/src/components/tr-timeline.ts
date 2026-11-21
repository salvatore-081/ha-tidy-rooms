// A room's day: the windows of its passes, the cleanings done, quiet hours and now.

import { element } from "../define";
import { LitElement, css, html, nothing } from "lit";
import { property } from "lit/decorators.js";
import { type FormatContext, clockMinutes, dayMinutes } from "../format";
import { passDescription } from "./tr-passes";
import type { PassSnapshot } from "../types";

const DAY = 24 * 60;
const pct = (minutes: number) => `${(minutes / DAY) * 100}%`;

/** Quiet hours as [start, end) ranges within the day (one or two). */
export const quietRanges = (start: string | null, end: string | null): Array<[number, number]> => {
  const a = clockMinutes(start);
  const b = clockMinutes(end);
  if (a === null || b === null || a === b) return [];
  return a < b
    ? [[a, b]]
    : [
        [0, b],
        [a, DAY],
      ];
};

@element("tr-timeline")
export class TrTimeline extends LitElement {
  @property({ attribute: false }) passes: PassSnapshot[] = [];
  @property({ attribute: false }) ctx!: FormatContext;
  @property({ attribute: false }) quietStart: string | null = null;
  @property({ attribute: false }) quietEnd: string | null = null;
  /** Hour labels under the bar. */
  @property({ type: Boolean }) labels = false;

  static styles = css`
    :host {
      display: block;
    }
    .track {
      position: relative;
      height: calc(var(--rows) * 10px + 6px);
      border-radius: 6px;
      background: color-mix(in srgb, var(--primary-text-color, #212121) 5%, transparent);
      overflow: hidden;
    }
    .quiet {
      position: absolute;
      top: 0;
      bottom: 0;
      background: repeating-linear-gradient(
        135deg,
        color-mix(in srgb, var(--primary-text-color, #212121) 9%, transparent) 0 3px,
        transparent 3px 7px
      );
    }
    .window {
      position: absolute;
      height: 6px;
      border-radius: 3px;
      background: color-mix(in srgb, var(--primary-color, #03a9f4) 35%, transparent);
      box-sizing: border-box;
    }
    .window.loose {
      background: transparent;
      border: 1px dashed var(--primary-color, #03a9f4);
    }
    .window.done {
      background: color-mix(in srgb, var(--success-color, #43a047) 40%, transparent);
    }
    .window.skipped {
      background: color-mix(in srgb, var(--disabled-text-color, #bdbdbd) 50%, transparent);
      border: none;
    }
    .mark {
      position: absolute;
      width: 10px;
      height: 10px;
      margin-left: -5px;
      border-radius: 50%;
      background: var(--success-color, #43a047);
      box-shadow: 0 0 0 2px var(--card-background-color, #fff);
    }
    .now {
      position: absolute;
      top: 0;
      bottom: 0;
      width: 2px;
      margin-left: -1px;
      background: var(--error-color, #db4437);
    }
    .hours {
      position: relative;
      height: 14px;
      margin-top: 2px;
      font-size: 0.7rem;
      color: var(--secondary-text-color, #727272);
    }
    .hours span {
      position: absolute;
      transform: translateX(-50%);
    }
    .hours span:first-child {
      transform: none;
    }
    .hours span:last-child {
      transform: translateX(-100%);
    }
  `;

  render() {
    const today = this.passes.filter((p) => p.status !== "not_today");
    const rows = Math.max(today.length, 1);
    const now = dayMinutes(this.ctx.now, this.ctx);
    return html`
      <div class="track" style="--rows:${rows}" role="img" aria-label=${this._label(today)}>
        ${quietRanges(this.quietStart, this.quietEnd).map(
          ([a, b]) => html`<div class="quiet" style="left:${pct(a)};width:${pct(b - a)}"></div>`,
        )}
        ${today.map((p, i) => {
          const start = clockMinutes(p.start) ?? 0;
          const end = clockMinutes(p.end) ?? DAY;
          const top = `${3 + i * 10}px`;
          const cls = [
            p.status === "done" ? "done" : p.status === "skipped" ? "skipped" : "",
            p.forced ? "" : "loose",
          ].join(" ");
          const done = p.status === "done" ? dayMinutes(p.done_at, this.ctx) : null;
          return html`<div
              class="window ${cls}"
              style="top:${top};left:${pct(start)};width:${pct(Math.max(end - start, 8))}"
              title=${passDescription(p, this.ctx)}
            ></div>
            ${
              done !== null
                ? html`<div class="mark" style="top:${3 + i * 10 - 2}px;left:${pct(done)}"></div>`
                : nothing
            }`;
        })}
        ${now !== null ? html`<div class="now" style="left:${pct(now)}"></div>` : nothing}
      </div>
      ${
        this.labels
          ? html`<div class="hours" aria-hidden="true">
              ${[0, 6, 12, 18, 24].map(
                (h) => html`<span style="left:${pct(h * 60)}">${String(h).padStart(2, "0")}</span>`,
              )}
            </div>`
          : nothing
      }
    `;
  }

  private _label(today: PassSnapshot[]): string {
    return today.map((p) => passDescription(p, this.ctx)).join("; ");
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tr-timeline": TrTimeline;
  }
}
