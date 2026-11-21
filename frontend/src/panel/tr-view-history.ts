// History tab: jobs of the last 7 or 30 days, with a summary per room.

import { LitElement, type PropertyValues, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { errorMessage, fetchHistory } from "../api";
import { type FormatContext, formatDayTime, formatDuration, formatTime } from "../format";
import { shared, tokens } from "../styles";
import type { HomeAssistant, JobRecord, LoadedSnapshot } from "../types";
import { RESULT_TONE } from "./tr-room-editor";

export interface RoomSummary {
  room_id: string;
  room: string;
  full: number;
  vacuum: number;
  interrupted: number;
  failed: number;
  stopped: number;
  minutes: number;
}

/** Totals per room; a full pass counts once, as full. */
export const summarize = (jobs: JobRecord[]): RoomSummary[] => {
  const byRoom = new Map<string, RoomSummary>();
  for (const job of jobs) {
    const s = byRoom.get(job.room_id) ?? {
      room_id: job.room_id,
      room: job.room,
      full: 0,
      vacuum: 0,
      interrupted: 0,
      failed: 0,
      stopped: 0,
      minutes: 0,
    };
    if (job.result === "done") {
      if (job.kind === "full") s.full += 1;
      else s.vacuum += 1;
      s.minutes += Math.max(0, (Date.parse(job.ended) - Date.parse(job.started)) / 60_000);
    } else {
      s[job.result] += 1;
    }
    byRoom.set(job.room_id, s);
  }
  return [...byRoom.values()].sort((a, b) => a.room.localeCompare(b.room));
};

@customElement("tr-view-history")
export class TrViewHistory extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @property({ attribute: false }) snapshot!: LoadedSnapshot;
  @property({ attribute: false }) ctx!: FormatContext;
  @property({ type: Boolean }) narrow = false;

  @state() private _days = 7;
  @state() private _room = "";
  @state() private _jobs?: JobRecord[];
  @state() private _error?: string;
  private _lastJobKey?: string;

  static styles = [
    tokens,
    shared,
    css`
      :host {
        display: grid;
        gap: var(--tr-gap);
        max-width: 1100px;
        margin: 0 auto;
      }
      .filters {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        align-items: center;
      }
      .segmented {
        display: inline-flex;
        border: 1px solid var(--tr-border);
        border-radius: 18px;
        overflow: hidden;
      }
      .segmented button {
        border: none;
        background: transparent;
        color: var(--tr-text);
        font: inherit;
        font-size: 0.9rem;
        padding: 0 16px;
        min-height: 36px;
        cursor: pointer;
      }
      .segmented button + button {
        border-left: 1px solid var(--tr-border);
      }
      .segmented button[aria-pressed="true"] {
        background: color-mix(in srgb, var(--tr-primary) 16%, transparent);
        color: var(--tr-primary);
        font-weight: 500;
      }
      select {
        font: inherit;
        font-size: 0.9rem;
        min-height: 36px;
        padding: 0 12px;
        border-radius: 18px;
        border: 1px solid var(--tr-border);
        background: var(--tr-card-bg);
        color: var(--tr-text);
      }
      .summary {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
        gap: 12px;
      }
      .stat {
        padding: 14px 16px;
      }
      .stat .room {
        font-weight: 500;
        margin-bottom: 8px;
      }
      .stat .nums {
        display: flex;
        gap: 16px;
        flex-wrap: wrap;
        font-size: 0.9rem;
      }
      .stat .nums span {
        display: inline-flex;
        align-items: center;
        gap: 4px;
      }
      .stat ha-icon {
        --mdc-icon-size: 18px;
        color: var(--tr-muted);
      }
      .stat .problems {
        margin-top: 6px;
        font-size: 0.8rem;
        color: var(--tr-muted);
      }
      table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.9rem;
      }
      th {
        text-align: left;
        font-weight: 500;
        color: var(--tr-muted);
        padding: 12px 16px;
        border-bottom: 1px solid var(--tr-border);
      }
      td {
        padding: 10px 16px;
        border-bottom: 1px solid var(--tr-border);
        vertical-align: middle;
      }
      tr:last-child td {
        border-bottom: none;
      }
      td.num {
        font-variant-numeric: tabular-nums;
        white-space: nowrap;
      }
      .flags ha-icon {
        --mdc-icon-size: 18px;
        color: var(--tr-muted);
        margin-right: 4px;
      }
      .list .item {
        display: flex;
        gap: 12px;
        align-items: center;
        padding: 12px 16px;
      }
      .list .item + .item {
        border-top: 1px solid var(--tr-border);
      }
      .list .main {
        flex: 1;
        min-width: 0;
      }
      .list .secondary {
        color: var(--tr-muted);
        font-size: 0.85rem;
      }
    `,
  ];

  protected willUpdate(changed: PropertyValues) {
    // Reload when a job ends (the snapshot's last result of a room changes).
    const key =
      this.snapshot.rooms
        .map((r) => `${r.id}:${r.last_full}:${r.last_vacuum}:${r.last_result}`)
        .join("|") + (this.snapshot.job ? "J" : "");
    if (changed.has("_days") || changed.has("_room") || key !== this._lastJobKey) {
      this._lastJobKey = key;
      this._load();
    }
  }

  private async _load() {
    try {
      const res = await fetchHistory(
        this.hass,
        this.snapshot.entry_id,
        this._days,
        this._room || undefined,
      );
      this._jobs = res.jobs;
      this._error = undefined;
    } catch (err) {
      this._error = errorMessage(err);
    }
  }

  render() {
    const { t } = this.ctx;
    const jobs = this._jobs;
    return html`
      <div class="filters">
        <div class="segmented" role="group" aria-label=${t("history.period")}>
          ${[7, 30].map(
            (days) =>
              html`<button
                aria-pressed=${this._days === days ? "true" : "false"}
                @click=${() => (this._days = days)}
              >
                ${t("history.days", { n: days })}
              </button>`,
          )}
        </div>
        <select
          aria-label=${t("history.room")}
          @change=${(ev: Event) => (this._room = (ev.target as HTMLSelectElement).value)}
        >
          <option value="" ?selected=${!this._room}>${t("history.all_rooms")}</option>
          ${this.snapshot.rooms.map(
            (r) => html`<option value=${r.id} ?selected=${this._room === r.id}>${r.name}</option>`,
          )}
        </select>
      </div>
      ${this._error ? html`<div class="error-box">${this._error}</div>` : nothing}
      ${
        jobs === undefined
          ? html`<div class="muted">${t("panel.loading")}</div>`
          : jobs.length === 0
            ? html`<div class="card empty-state">
                <ha-icon icon="mdi:history"></ha-icon>${t("history.empty")}
              </div>`
            : html`${this._summary(jobs)} ${this.narrow ? this._list(jobs) : this._table(jobs)}`
      }
    `;
  }

  private _summary(jobs: JobRecord[]) {
    const { t } = this.ctx;
    return html`<div class="summary">
      ${summarize(jobs).map((s) => {
        const problems = [
          s.interrupted ? t("history.n_interrupted", { n: s.interrupted }) : "",
          s.failed ? t("history.n_failed", { n: s.failed }) : "",
          s.stopped ? t("history.n_stopped", { n: s.stopped }) : "",
        ].filter(Boolean);
        return html`<div class="card stat">
          <div class="room">${s.room}</div>
          <div class="nums">
            <span title=${t("kind.full")}><ha-icon icon="mdi:water"></ha-icon>${s.full}</span>
            <span title=${t("kind.vacuum")}><ha-icon icon="mdi:broom"></ha-icon>${s.vacuum}</span>
            <span title=${t("history.total_time")}
              ><ha-icon icon="mdi:timer-outline"></ha-icon
              >${formatDuration(s.minutes * 60_000, t)}</span
            >
          </div>
          ${problems.length ? html`<div class="problems">${problems.join(" · ")}</div>` : nothing}
        </div>`;
      })}
    </div>`;
  }

  private _flags(job: JobRecord) {
    const { t } = this.ctx;
    return html`<span class="flags">
      ${
        job.manual
          ? html`<ha-icon icon="mdi:gesture-tap" title=${t("job.manual")}></ha-icon>`
          : job.forced
            ? html`<ha-icon icon="mdi:clock-alert-outline" title=${t("job.forced")}></ha-icon>`
            : nothing
      }
      ${job.quiet ? html`<ha-icon icon="mdi:volume-low" title=${t("job.quiet")}></ha-icon>` : nothing}
      ${
        job.attempts > 1
          ? html`<ha-icon
              icon="mdi:replay"
              title=${t("job.attempts", { n: job.attempts })}
            ></ha-icon>`
          : nothing
      }
    </span>`;
  }

  private _duration(job: JobRecord) {
    return formatDuration(Date.parse(job.ended) - Date.parse(job.started), this.ctx.t);
  }

  private _table(jobs: JobRecord[]) {
    const { t } = this.ctx;
    return html`<div class="card">
      <table>
        <thead>
          <tr>
            <th>${t("history.started")}</th>
            <th>${t("history.room")}</th>
            <th>${t("history.kind")}</th>
            <th>${t("history.duration")}</th>
            <th>${t("history.result")}</th>
            <th><span class="sr-only">${t("history.details")}</span></th>
          </tr>
        </thead>
        <tbody>
          ${jobs.map(
            (job) =>
              html`<tr>
                <td class="num">
                  ${formatDayTime(job.started, this.ctx)}–${formatTime(job.ended, this.ctx)}
                </td>
                <td>${job.room}</td>
                <td>${t(`kind.${job.kind}`)}</td>
                <td class="num">${this._duration(job)}</td>
                <td>
                  <span class="chip tone-${RESULT_TONE[job.result]}"
                    >${t(`result.${job.result}`)}</span
                  >
                </td>
                <td>${this._flags(job)}</td>
              </tr>`,
          )}
        </tbody>
      </table>
    </div>`;
  }

  private _list(jobs: JobRecord[]) {
    const { t } = this.ctx;
    return html`<div class="card list">
      ${jobs.map(
        (job) =>
          html`<div class="item">
            <div class="main">
              ${job.room} · ${t(`kind.${job.kind}`)}
              <div class="secondary">
                ${formatDayTime(job.started, this.ctx)} · ${this._duration(job)} ${this._flags(job)}
              </div>
            </div>
            <span class="chip tone-${RESULT_TONE[job.result]}">${t(`result.${job.result}`)}</span>
          </div>`,
      )}
    </div>`;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tr-view-history": TrViewHistory;
  }
}
