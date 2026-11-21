// Dashboard card: the robot and its rooms in compact form.

import { element } from "../define";
import { LitElement, type PropertyValues, css, html, nothing } from "lit";
import { property, state } from "lit/decorators.js";
import "../components/tr-passes";
import { errorMessage, listEntries, subscribeSnapshot } from "../api";
import {
  type FormatContext,
  formatContext,
  formatDuration,
  outlookText,
  statusIcon,
  statusTone,
  waitText,
} from "../format";
import { type Localize, localizer } from "../localize";
import { navigate } from "../nav";
import { shared, tokens } from "../styles";
import type { HomeAssistant, LoadedSnapshot, RoomSnapshot, Snapshot } from "../types";

export interface TidyRoomsCardConfig {
  type: string;
  entry_id?: string;
  title?: string;
  rooms?: string[];
  show_robot?: boolean;
  show_outlook?: boolean;
}

const TICK_MS = 60_000;

@element("tidy-rooms-card")
export class TidyRoomsCard extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @state() private _config!: TidyRoomsCardConfig;
  @state() private _entryId?: string;
  @state() private _snapshot?: Snapshot;
  @state() private _error?: string;
  @state() private _now = new Date();
  private _unsub?: Promise<() => void>;
  private _subscribedTo?: string;
  private _timer?: number;

  static getConfigElement() {
    return document.createElement("tidy-rooms-card-editor");
  }

  static getStubConfig(): Partial<TidyRoomsCardConfig> {
    return { show_robot: true, show_outlook: true };
  }

  setConfig(config: TidyRoomsCardConfig) {
    if (!config) throw new Error("Invalid configuration");
    this._config = { show_robot: true, show_outlook: true, ...config };
    if (this._entryId && config.entry_id && config.entry_id !== this._entryId) {
      this._entryId = config.entry_id;
    }
  }

  getCardSize() {
    const rooms = this._visibleRooms().length || 3;
    return (this._config?.show_robot ? 2 : 1) + rooms;
  }

  getGridOptions() {
    const rooms = this._visibleRooms().length || 3;
    return { columns: 12, min_columns: 6, rows: (this._config?.show_robot ? 2 : 1) + rooms };
  }

  static styles = [
    tokens,
    shared,
    css`
      ha-card {
        overflow: hidden;
        height: 100%;
      }
      .header {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 12px 16px;
      }
      .avatar {
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
        font-size: 1rem;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .sub {
        color: var(--tr-muted);
        font-size: 0.85rem;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .auto {
        color: var(--tr-muted);
      }
      .auto.on {
        color: var(--tr-primary);
      }
      .rooms {
        padding: 0 0 8px;
      }
      .header + .rooms {
        border-top: 1px solid var(--tr-border);
        padding-top: 4px;
      }
      .room {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 8px 16px;
      }
      .room.link {
        cursor: pointer;
      }
      .room.link:hover {
        background: color-mix(in srgb, var(--tr-text) 4%, transparent);
      }
      .room .icon {
        flex: none;
        color: var(--tone);
      }
      .room .text {
        flex: 1;
        min-width: 0;
      }
      .room .rname {
        font-weight: 500;
        font-size: 0.95rem;
      }
      .room .detail {
        color: var(--tr-muted);
        font-size: 0.8rem;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .room .passes {
        display: flex;
        flex-direction: column;
        align-items: flex-end;
        gap: 2px;
      }
      .message {
        padding: 16px;
        color: var(--tr-muted);
      }
    `,
  ];

  connectedCallback() {
    super.connectedCallback();
    this._timer = window.setInterval(() => (this._now = new Date()), TICK_MS);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    window.clearInterval(this._timer);
    this._unsub?.then((u) => u()).catch(() => undefined);
    this._unsub = undefined;
    this._subscribedTo = undefined;
  }

  protected willUpdate(changed: PropertyValues) {
    if (!this.hass || !this._config) return;
    const wanted = this._config.entry_id;
    if (wanted && wanted !== this._entryId) this._entryId = wanted;
    if (!this._entryId && !wanted && changed.has("hass") && this._error === undefined) {
      this._error = "";
      listEntries(this.hass)
        .then((entries) => {
          this._entryId = entries[0]?.entry_id;
          this._error = entries.length ? undefined : "no_entries";
        })
        .catch((err) => (this._error = errorMessage(err)));
    }
    if (this._entryId && this._subscribedTo !== this._entryId && this.isConnected) {
      this._unsub?.then((u) => u()).catch(() => undefined);
      const entryId = this._entryId;
      this._subscribedTo = entryId;
      this._unsub = subscribeSnapshot(this.hass, entryId, (snap) => {
        if (this._subscribedTo === entryId) {
          this._snapshot = snap;
          this._now = new Date();
        }
      });
      this._unsub.catch(
        (err) =>
          (this._error =
            (err as { code?: string })?.code === "not_found" ? "not_found" : errorMessage(err)),
      );
    }
  }

  private get _t(): Localize {
    return localizer(this.hass?.locale?.language || this.hass?.language);
  }

  private _visibleRooms(): RoomSnapshot[] {
    const snap = this._snapshot;
    if (!snap?.loaded) return [];
    const wanted = this._config?.rooms;
    return wanted?.length ? snap.rooms.filter((r) => wanted.includes(r.id)) : snap.rooms;
  }

  render() {
    if (!this._config || !this.hass) return nothing;
    const t = this._t;
    const snap = this._snapshot;
    let body;
    if (this._error === "no_entries" || this._error === "not_found")
      body = html`<div class="message">${t(`card.${this._error}`)}</div>`;
    else if (this._error) body = html`<div class="message">${this._error}</div>`;
    else if (!snap) body = html`<div class="message">${t("card.loading")}</div>`;
    else if (!snap.loaded) body = html`<div class="message">${t("card.not_loaded")}</div>`;
    else body = this._content(snap, formatContext(this.hass, t, this._now));
    return html`<ha-card>${body}</ha-card>`;
  }

  private _content(snap: LoadedSnapshot, ctx: FormatContext) {
    const { t } = ctx;
    const robot = snap.robot;
    const admin = this.hass.user?.is_admin ?? false;
    const stateObj = this.hass.states[robot.entity_id];
    const stateText =
      stateObj && this.hass.formatEntityState
        ? this.hass.formatEntityState(stateObj)
        : (robot.state ?? "");
    const job = snap.job;
    const sub = job
      ? `${t(`job.title_${job.kind}`, { room: job.room })} · ${formatDuration(
          ctx.now.getTime() - new Date(job.created).getTime(),
          t,
        )}`
      : [stateText, robot.battery !== null ? `${robot.battery}%` : ""].filter(Boolean).join(" · ");
    const tone = !robot.available ? "error" : job ? "active" : snap.enabled ? "ready" : "off";
    return html`
      ${
        this._config.show_robot
          ? html`<div class="header">
              <div class="avatar tone-${tone}">
                <ha-icon
                  icon=${robot.available ? "mdi:robot-vacuum" : "mdi:robot-vacuum-off"}
                ></ha-icon>
              </div>
              <div class="title">
                <div class="name">${this._config.title || robot.name}</div>
                <div class="sub">${sub}</div>
              </div>
              <ha-icon
                class="auto ${snap.enabled ? "on" : ""}"
                icon=${snap.enabled ? "mdi:autorenew" : "mdi:pause-circle-outline"}
                title=${t("robot.automatic")}
              ></ha-icon>
            </div>`
          : this._config.title
            ? html`<div class="header"><div class="name">${this._config.title}</div></div>`
            : nothing
      }
      <div class="rooms">
        ${this._visibleRooms().map((room) => {
          const tone = statusTone(room);
          const outlook = this._config.show_outlook ? outlookText(room, ctx) : "";
          const detail =
            room.status === "done" || room.status === "cleaning" || !outlook
              ? waitText(room, snap, ctx)
              : outlook;
          return html`<div
            class="room tone-${tone} ${admin ? "link" : ""}"
            @click=${admin ? () => this._open(room) : undefined}
          >
            <ha-icon class="icon" .icon=${statusIcon(room)}></ha-icon>
            <div class="text">
              <div class="rname">${room.name}</div>
              <div class="detail">${detail}</div>
            </div>
            <div class="passes">
              ${
                room.full_per_day
                  ? html`<tr-passes
                      .done=${room.full_today}
                      .target=${room.full_per_day}
                      icon="mdi:water"
                      .label=${t("kind.full")}
                    ></tr-passes>`
                  : nothing
              }
              ${
                room.vacuum_per_day
                  ? html`<tr-passes
                      .done=${room.vacuum_today}
                      .target=${room.vacuum_per_day}
                      icon="mdi:broom"
                      .label=${t("kind.vacuum_passes")}
                    ></tr-passes>`
                  : nothing
              }
            </div>
          </div>`;
        })}
      </div>
    `;
  }

  private _open(room: RoomSnapshot) {
    const query = this._config.entry_id ? `?entry=${this._config.entry_id}` : "";
    navigate(`/tidy-rooms/rooms/${room.id}${query}`);
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tidy-rooms-card": TidyRoomsCard;
  }
}
