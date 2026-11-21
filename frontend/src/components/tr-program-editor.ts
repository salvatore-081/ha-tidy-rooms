// The cleaning program of a room: its passes, in order, each edited with ha-form.

import { element } from "../define";
import { LitElement, css, html, nothing } from "lit";
import { property } from "lit/decorators.js";
import { confirmDialog } from "./tr-confirm";
import { type FormatContext, clockMinutes, formatClock } from "../format";
import { quietRanges } from "./tr-timeline";
import { formCallbacks } from "../form";
import { shared, tokens } from "../styles";
import type { FormField, HomeAssistant, PassData } from "../types";

/** Errors of one pass, from the save errors keyed "passes.<i>.<field>". */
export const passErrors = (
  errors: Record<string, string>,
  index: number,
): Record<string, string> => {
  const prefix = `passes.${index}.`;
  return Object.fromEntries(
    Object.entries(errors)
      .filter(([key]) => key.startsWith(prefix))
      .map(([key, value]) => [key.slice(prefix.length), value]),
  );
};

/** True if the pass's window falls entirely within do not disturb (it can never run). */
export const windowInDnd = (
  p: PassData,
  quietStart: string | null,
  quietEnd: string | null,
): boolean => {
  const ranges = quietRanges(quietStart, quietEnd);
  if (!ranges.length) return false;
  const start = clockMinutes(p.start as string | undefined) ?? 0;
  const end = clockMinutes(p.end as string | undefined) ?? 24 * 60;
  if (start >= end) return false;
  // Every minute of [start, end) inside one of the ranges?
  let at = start;
  for (const [a, b] of ranges) if (a <= at && at < b) at = b;
  for (const [a, b] of ranges) if (a <= at && at < b) at = b;
  return at >= end;
};

/** Times without seconds: a pass works to the minute. */
export const withoutSeconds = (schema: FormField[]): FormField[] =>
  schema.map((f) =>
    f.selector && "time" in f.selector
      ? { ...f, selector: { time: { ...(f.selector.time as object), no_second: true } } }
      : f,
  );

/** "Vacuum · until 19:00 · Mon, Tue": one line for a pass being edited. */
export const passSummary = (p: PassData, ctx: FormatContext): string => {
  const { t } = ctx;
  const start = formatClock(p.start as string | undefined, ctx);
  const end = formatClock(p.end as string | undefined, ctx);
  const window =
    start && end
      ? t("pass.window", { start, end })
      : end
        ? t("pass.until", { time: end })
        : start
          ? t("pass.from", { time: start })
          : t("pass.any_time");
  const days = (p.days as string[] | undefined) ?? [];
  const parts = [ctx.mode(p.work_mode as string | undefined), window];
  if (days.length && days.length < 7)
    parts.push(days.map((d) => t(`selector.weekday.short.${d}`)).join(", "));
  return parts.join(" · ");
};

@element("tr-program-editor")
export class TrProgramEditor extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @property({ attribute: false }) ctx!: FormatContext;
  @property({ attribute: false }) schema: FormField[] = [];
  @property({ attribute: false }) passes: PassData[] = [];
  @property({ attribute: false }) defaults: Record<string, unknown> = {};
  @property({ attribute: false }) errors: Record<string, string> = {};
  @property({ type: Number }) max = 6;
  /** Do not disturb, to warn about windows that can never run. */
  @property({ attribute: false }) quietStart: string | null = null;
  @property({ attribute: false }) quietEnd: string | null = null;
  @property({ type: Boolean }) disabled = false;

  static styles = [
    tokens,
    shared,
    css`
      :host {
        display: block;
      }
      .pass {
        border: 1px solid var(--tr-border);
        border-radius: var(--tr-radius);
        margin-bottom: 12px;
      }
      .pass.error {
        border-color: var(--error-color, #db4437);
      }
      summary {
        list-style: none;
        cursor: pointer;
      }
      summary::-webkit-details-marker {
        display: none;
      }
      .head {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 4px 8px 4px 16px;
      }
      .head .chevron {
        color: var(--tr-muted);
        transition: transform 0.15s;
      }
      details[open] .head .chevron {
        transform: rotate(90deg);
      }
      .head .n {
        font-weight: 500;
      }
      .head .summary {
        flex: 1;
        min-width: 0;
        color: var(--tr-muted);
        font-size: 0.9rem;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .body {
        padding: 0 16px 12px;
      }
      .empty {
        margin: 0 0 12px;
        color: var(--tr-muted);
      }
      .error-text {
        margin: 0 0 12px;
        color: var(--error-color, #db4437);
      }
      .warning {
        display: flex;
        gap: 8px;
        align-items: flex-start;
        margin: 0 16px 8px;
        color: var(--warning-color, #ffa600);
        font-size: 0.9rem;
      }
      .warning ha-icon {
        --mdc-icon-size: 18px;
        flex: none;
      }
    `,
  ];

  render() {
    const { t } = this.ctx;
    const cb = formCallbacks(t);
    const listError = this.errors.passes;
    return html`
      ${listError ? html`<p class="error-text">${cb.computeError(listError)}</p>` : nothing}
      ${
        this.passes.length
          ? this.passes.map((p, i) => this._pass(p, i))
          : html`<p class="empty">${t("program.empty")}</p>`
      }
      <button
        class="btn"
        ?disabled=${this.disabled || this.passes.length >= this.max}
        @click=${this._add}
      >
        <ha-icon icon="mdi:plus"></ha-icon>${t("program.add")}
      </button>
    `;
  }

  private _pass(p: PassData, i: number) {
    const { t } = this.ctx;
    const cb = formCallbacks(t);
    const errors = passErrors(this.errors, i);
    const n = i + 1;
    const failed = Object.keys(errors).length > 0;
    // Closed by default; open when new or wrong (the user's toggles are kept).
    return html`<details class="pass ${failed ? "error" : ""}" ?open=${failed || !p.id}>
      <summary class="head">
        <ha-icon class="chevron" icon="mdi:chevron-right"></ha-icon>
        <span class="n">${t("program.pass_n", { n })}</span>
        <span class="summary">${passSummary(p, this.ctx)}</span>
        <button
          class="icon-btn"
          ?disabled=${this.disabled || i === 0}
          aria-label=${t("program.move_up", { n })}
          title=${t("program.move_up", { n })}
          @click=${(ev: Event) => this._move(ev, i, -1)}
        >
          <ha-icon icon="mdi:chevron-up"></ha-icon>
        </button>
        <button
          class="icon-btn"
          ?disabled=${this.disabled || i === this.passes.length - 1}
          aria-label=${t("program.move_down", { n })}
          title=${t("program.move_down", { n })}
          @click=${(ev: Event) => this._move(ev, i, 1)}
        >
          <ha-icon icon="mdi:chevron-down"></ha-icon>
        </button>
        <button
          class="icon-btn delete"
          ?disabled=${this.disabled}
          aria-label=${t("program.remove", { n })}
          title=${t("program.remove", { n })}
          @click=${(ev: Event) => this._remove(ev, i)}
        >
          <ha-icon icon="mdi:delete-outline"></ha-icon>
        </button>
      </summary>
      ${
        windowInDnd(p, this.quietStart, this.quietEnd)
          ? html`<div class="warning" role="note">
              <ha-icon icon="mdi:alert-outline"></ha-icon>${t("program.window_in_dnd")}
            </div>`
          : nothing
      }
      <div class="body">
        <ha-form
          .hass=${this.hass}
          .data=${p}
          .schema=${withoutSeconds(this.schema)}
          .error=${errors}
          .computeLabel=${cb.computeLabel}
          .computeHelper=${cb.computeHelper}
          .computeError=${cb.computeError}
          .localizeValue=${cb.localizeValue}
          .disabled=${this.disabled}
          @value-changed=${(ev: CustomEvent<{ value: Record<string, unknown> }>) =>
            this._changed(i, ev.detail.value)}
        ></ha-form>
      </div>
    </details>`;
  }

  private _emit(passes: PassData[]) {
    this.dispatchEvent(new CustomEvent("passes-changed", { detail: { passes } }));
  }

  private _changed(index: number, value: Record<string, unknown>) {
    const pass: PassData = { ...this.passes[index], ...value };
    for (const [key, v] of Object.entries(value))
      if (v === undefined || v === "" || (Array.isArray(v) && v.length === 0)) delete pass[key];
    this._emit(this.passes.map((p, i) => (i === index ? pass : p)));
  }

  private _add() {
    // A new pass starts after the last one: same work mode, no window yet.
    const last = this.passes[this.passes.length - 1];
    const pass: PassData = { ...this.defaults };
    if (last?.work_mode) pass.work_mode = last.work_mode;
    this._emit([...this.passes, pass]);
  }

  private _move(ev: Event, index: number, delta: number) {
    ev.preventDefault(); // a button in the summary must not toggle the pass
    const passes = [...this.passes];
    const [moved] = passes.splice(index, 1);
    passes.splice(index + delta, 0, moved);
    this._emit(passes);
  }

  private async _remove(ev: Event, index: number) {
    ev.preventDefault();
    const { t } = this.ctx;
    const ok = await confirmDialog(this.renderRoot as ShadowRoot, {
      title: t("program.remove_title", { n: index + 1 }),
      text: passSummary(this.passes[index], this.ctx),
      confirm: t("common.delete"),
      cancel: t("common.cancel"),
      destructive: true,
    });
    if (ok) this._emit(this.passes.filter((_, i) => i !== index));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tr-program-editor": TrProgramEditor;
  }
}
