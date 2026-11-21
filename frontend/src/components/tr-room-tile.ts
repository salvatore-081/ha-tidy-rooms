// One room: status, why it waits, today's passes, last pass and outlook.

import { element } from "../define";
import { LitElement, css, html, nothing } from "lit";
import { property } from "lit/decorators.js";
import "./tr-passes";
import {
  type FormatContext,
  formatDayTime,
  lastPass,
  outlookText,
  statusIcon,
  statusLabel,
  statusTone,
  waitText,
} from "../format";
import { shared, tokens } from "../styles";
import type { CleanKind, HomeAssistant, LoadedSnapshot, RoomSnapshot } from "../types";

@element("tr-room-tile")
export class TrRoomTile extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @property({ attribute: false }) snapshot!: LoadedSnapshot;
  @property({ attribute: false }) room!: RoomSnapshot;
  @property({ attribute: false }) ctx!: FormatContext;
  @property({ type: Boolean }) admin = false;
  @property({ type: Boolean }) next = false;

  static styles = [
    tokens,
    shared,
    css`
      :host {
        display: block;
      }
      .card {
        display: flex;
        flex-direction: column;
        height: 100%;
        box-sizing: border-box;
      }
      .card.next {
        border-color: var(--tr-primary);
      }
      .head {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 14px 16px 0;
        cursor: pointer;
        border-radius: var(--tr-radius) var(--tr-radius) 0 0;
      }
      .head:focus-visible {
        outline: 2px solid var(--tr-primary);
        outline-offset: -2px;
      }
      .icon {
        flex: none;
        display: flex;
        align-items: center;
        justify-content: center;
        width: 40px;
        height: 40px;
        border-radius: 50%;
        color: var(--tone);
        background: color-mix(in srgb, var(--tone) 14%, transparent);
      }
      .title {
        flex: 1;
        min-width: 0;
      }
      .name {
        font-weight: 500;
        font-size: 1.05rem;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .status {
        font-size: 0.85rem;
        color: var(--tone);
      }
      .chevron {
        color: var(--tr-muted);
      }
      .body {
        flex: 1;
        padding: 10px 16px 0;
      }
      .wait {
        line-height: 1.4;
      }
      .passes {
        display: flex;
        flex-wrap: wrap;
        gap: 6px 20px;
        margin-top: 12px;
      }
      .facts {
        display: grid;
        gap: 4px;
        margin-top: 12px;
        font-size: 0.85rem;
        color: var(--tr-muted);
      }
      .facts ha-icon {
        --mdc-icon-size: 16px;
        margin-right: 6px;
        vertical-align: -2px;
      }
      .next-badge {
        font-size: 0.75rem;
        font-weight: 500;
        color: var(--tr-primary);
        text-transform: uppercase;
        letter-spacing: 0.04em;
      }
      .actions {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        padding: 12px 16px 14px;
      }
      .actions .btn {
        flex: 1;
      }
    `,
  ];

  render() {
    const r = this.room;
    const { t } = this.ctx;
    const tone = statusTone(r);
    const last = lastPass(r);
    const outlook = outlookText(r, this.ctx);
    const area = this.hass.areas?.[r.area_id];
    const busy = this.snapshot.job !== null || !this.snapshot.robot.available;
    return html`
      <div class="card ${this.next ? "next" : ""}">
        <div
          class="head tone-${tone}"
          role="button"
          tabindex="0"
          aria-label=${t("room.open", { room: r.name })}
          @click=${this._open}
          @keydown=${this._key}
        >
          <div class="icon">
            <ha-icon
              .icon=${r.status === "cleaning" || !area?.icon ? statusIcon(r) : area.icon}
            ></ha-icon>
          </div>
          <div class="title">
            ${this.next ? html`<div class="next-badge">${t("room.next_badge")}</div>` : nothing}
            <div class="name">${r.name}</div>
            <div class="status">${statusLabel(r, t)}</div>
          </div>
          <ha-icon class="chevron" icon="mdi:chevron-right"></ha-icon>
        </div>
        <div class="body">
          <div class="wait">${waitText(r, this.snapshot, this.ctx)}</div>
          <div class="passes">
            ${
              r.full_per_day || r.full_today
                ? html`<tr-passes
                    .done=${r.full_today}
                    .target=${r.full_per_day}
                    icon="mdi:water"
                    .label=${t("kind.full")}
                    title=${t("kind.full")}
                  ></tr-passes>`
                : nothing
            }
            ${
              r.vacuum_per_day || r.vacuum_today
                ? html`<tr-passes
                    .done=${r.vacuum_today}
                    .target=${r.vacuum_per_day}
                    icon="mdi:broom"
                    .label=${t("kind.vacuum_passes")}
                    title=${t("kind.vacuum_passes")}
                  ></tr-passes>`
                : nothing
            }
          </div>
          <div class="facts">
            ${
              outlook && r.status !== "cleaning"
                ? html`<div><ha-icon icon="mdi:calendar-clock"></ha-icon>${outlook}</div>`
                : nothing
            }
            <div>
              <ha-icon icon="mdi:history"></ha-icon>${
                last
                  ? t(`room.last_${last.kind}`, { when: formatDayTime(last.at, this.ctx) })
                  : t("room.never")
              }
              ${
                r.last_result && r.last_result !== "done"
                  ? html` · ${t(`result.${r.last_result}`)}`
                  : nothing
              }
            </div>
          </div>
        </div>
        ${
          this.admin
            ? html`<div class="actions">
                ${
                  r.full_per_day
                    ? html`<button
                        class="btn"
                        ?disabled=${busy}
                        @click=${() => this._clean("full")}
                      >
                        <ha-icon icon="mdi:water"></ha-icon>${t("room.clean_full")}
                      </button>`
                    : nothing
                }
                <button class="btn" ?disabled=${busy} @click=${() => this._clean("vacuum")}>
                  <ha-icon icon="mdi:broom"></ha-icon>${t("room.clean_vacuum")}
                </button>
              </div>`
            : html`<div style="height:14px"></div>`
        }
      </div>
    `;
  }

  private _open() {
    this.dispatchEvent(
      new CustomEvent("open-room", {
        detail: { room: this.room.id },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _key(ev: KeyboardEvent) {
    if (ev.key === "Enter" || ev.key === " ") {
      ev.preventDefault();
      this._open();
    }
  }

  private _clean(kind: CleanKind) {
    this.dispatchEvent(
      new CustomEvent("clean-now", {
        detail: { room: this.room.id, kind },
        bubbles: true,
        composed: true,
      }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tr-room-tile": TrRoomTile;
  }
}
