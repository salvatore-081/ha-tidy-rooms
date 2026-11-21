// Rooms tab: the rooms in priority order, to reorder, include, edit, add or delete.

import { element } from "../define";
import { LitElement, css, html, nothing } from "lit";
import { property, state } from "lit/decorators.js";
import "../components/tr-switch";
import { deleteRoom, errorMessage, reorderRooms, setRoomEnabled } from "../api";
import { confirmDialog } from "../components/tr-confirm";
import { type FormatContext, passWindow, statusIcon, statusLabel, statusTone } from "../format";
import { navigate, notify, panelPath } from "../nav";
import { shared, tokens } from "../styles";
import type { HomeAssistant, LoadedSnapshot, RoomSnapshot } from "../types";

@element("tr-view-rooms")
export class TrViewRooms extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @property({ attribute: false }) snapshot!: LoadedSnapshot;
  @property({ attribute: false }) ctx!: FormatContext;
  @state() private _busy = false;

  static styles = [
    tokens,
    shared,
    css`
      :host {
        display: block;
        max-width: 900px;
        margin: 0 auto;
      }
      .intro {
        display: flex;
        align-items: center;
        gap: 16px;
        flex-wrap: wrap;
        margin: 0 4px 16px;
      }
      .intro p {
        flex: 1;
        min-width: 240px;
        margin: 0;
        color: var(--tr-muted);
        line-height: 1.5;
      }
      ul {
        list-style: none;
        margin: 0;
        padding: 0;
      }
      li {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 10px 8px 10px 4px;
      }
      li + li {
        border-top: 1px solid var(--tr-border);
      }
      .order {
        display: flex;
        flex-direction: column;
        flex: none;
      }
      .order .icon-btn {
        width: 32px;
        height: 28px;
        border-radius: 8px;
      }
      .rank {
        flex: none;
        width: 24px;
        text-align: center;
        font-weight: 500;
        color: var(--tr-muted);
        font-variant-numeric: tabular-nums;
      }
      .info {
        flex: 1;
        min-width: 0;
        cursor: pointer;
      }
      .name {
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
        font-weight: 500;
      }
      .summary {
        margin-top: 2px;
        font-size: 0.85rem;
        color: var(--tr-muted);
      }
      .summary .warn {
        color: var(--warning-color, #ffa600);
      }
      .summary span + span::before {
        content: " · ";
      }
      .off .name,
      .off .summary {
        opacity: 0.6;
      }
      @media (max-width: 600px) {
        .rank {
          display: none;
        }
        .delete {
          display: none;
        }
      }
    `,
  ];

  render() {
    const s = this.snapshot;
    const { t } = this.ctx;
    return html`
      <div class="intro">
        <p>${t("rooms.intro")}</p>
        <button class="btn filled" @click=${() => navigate(panelPath("/rooms/new"))}>
          <ha-icon icon="mdi:plus"></ha-icon>${t("rooms.add")}
        </button>
      </div>
      ${
        s.rooms.length
          ? html`<div class="card">
              <ul>
                ${s.rooms.map((room, i) => this._row(room, i))}
              </ul>
            </div>`
          : html`<div class="card empty-state">
              <ha-icon icon="mdi:floor-plan"></ha-icon>${t("overview.no_rooms")}
            </div>`
      }
    `;
  }

  private _row(room: RoomSnapshot, index: number) {
    const { t } = this.ctx;
    const count = this.snapshot.rooms.length;
    const tone = statusTone(room);
    const sensors = room.occupancy_sensors.length
      ? t("rooms.sensors", { n: room.occupancy_sensors.length })
      : room.proxy_sensors.length
        ? t("rooms.proxy", { n: room.proxy_sensors.length })
        : t("rooms.no_sensors");
    const program = room.passes.length
      ? t("rooms.program", {
          n: room.passes.length,
          passes: room.passes
            .map((p) => `${this.ctx.mode(p.work_mode)} ${passWindow(p, this.ctx)}`)
            .join(", "),
        })
      : t("rooms.no_program");
    return html`<li class=${room.enabled ? "" : "off"}>
      <div class="order">
        <button
          class="icon-btn"
          ?disabled=${index === 0 || this._busy}
          aria-label=${t("rooms.move_up", { room: room.name })}
          title=${t("rooms.move_up", { room: room.name })}
          @click=${() => this._move(index, -1)}
        >
          <ha-icon icon="mdi:chevron-up"></ha-icon>
        </button>
        <button
          class="icon-btn"
          ?disabled=${index === count - 1 || this._busy}
          aria-label=${t("rooms.move_down", { room: room.name })}
          title=${t("rooms.move_down", { room: room.name })}
          @click=${() => this._move(index, 1)}
        >
          <ha-icon icon="mdi:chevron-down"></ha-icon>
        </button>
      </div>
      <div class="rank">${index + 1}</div>
      <div class="info" @click=${() => this._edit(room)}>
        <div class="name">
          ${room.name}
          <span class="chip tone-${tone}"
            ><ha-icon .icon=${statusIcon(room)}></ha-icon>${statusLabel(room, t)}</span
          >
        </div>
        <div class="summary">
          <span>${sensors}</span><span class=${room.passes.length ? "" : "warn"}>${program}</span>
          ${room.custom_action ? html`<span>${t("rooms.custom_action")}</span>` : nothing}
        </div>
      </div>
      <tr-switch
        .checked=${room.enabled}
        .label=${t("rooms.include", { room: room.name })}
        @change=${(ev: CustomEvent<{ checked: boolean }>) => this._enable(room, ev.detail.checked)}
      ></tr-switch>
      <button
        class="icon-btn"
        aria-label=${t("rooms.edit", { room: room.name })}
        title=${t("rooms.edit", { room: room.name })}
        @click=${() => this._edit(room)}
      >
        <ha-icon icon="mdi:pencil-outline"></ha-icon>
      </button>
      <button
        class="icon-btn delete"
        aria-label=${t("rooms.delete", { room: room.name })}
        title=${t("rooms.delete", { room: room.name })}
        @click=${() => this._delete(room)}
      >
        <ha-icon icon="mdi:delete-outline"></ha-icon>
      </button>
    </li>`;
  }

  private _edit(room: RoomSnapshot) {
    navigate(panelPath(`/rooms/${room.id}`));
  }

  private async _move(index: number, delta: number) {
    const order = this.snapshot.rooms.map((r) => r.id);
    const [moved] = order.splice(index, 1);
    order.splice(index + delta, 0, moved);
    this._busy = true;
    try {
      await reorderRooms(this.hass, this.snapshot.entry_id, order);
    } catch (err) {
      notify(this, errorMessage(err));
    } finally {
      this._busy = false;
    }
  }

  private async _enable(room: RoomSnapshot, enabled: boolean) {
    try {
      await setRoomEnabled(this.hass, this.snapshot.entry_id, room.id, enabled);
    } catch (err) {
      notify(this, errorMessage(err));
    }
  }

  private async _delete(room: RoomSnapshot) {
    const { t } = this.ctx;
    const ok = await confirmDialog(this.renderRoot as ShadowRoot, {
      title: t("confirm.delete_title", { room: room.name }),
      text: t("confirm.delete_text"),
      confirm: t("common.delete"),
      cancel: t("common.cancel"),
      destructive: true,
    });
    if (!ok) return;
    try {
      await deleteRoom(this.hass, this.snapshot.entry_id, room.id);
      notify(this, t("toast.room_deleted", { room: room.name }));
    } catch (err) {
      notify(this, errorMessage(err));
    }
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tr-view-rooms": TrViewRooms;
  }
}
