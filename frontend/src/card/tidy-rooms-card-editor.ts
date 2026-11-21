// Visual editor of the card.

import { element } from "../define";
import { LitElement, type PropertyValues, html, nothing } from "lit";
import { property, state } from "lit/decorators.js";
import { listEntries, subscribeSnapshot } from "../api";
import { type Localize, localizer } from "../localize";
import type { EntrySummary, HomeAssistant, RoomSnapshot } from "../types";
import type { TidyRoomsCardConfig } from "./tidy-rooms-card";

@element("tidy-rooms-card-editor")
export class TidyRoomsCardEditor extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @state() private _config!: TidyRoomsCardConfig;
  @state() private _entries?: EntrySummary[];
  @state() private _rooms: RoomSnapshot[] = [];
  private _roomsFor?: string;

  setConfig(config: TidyRoomsCardConfig) {
    this._config = config;
  }

  private get _t(): Localize {
    return localizer(this.hass?.locale?.language || this.hass?.language);
  }

  protected willUpdate(changed: PropertyValues) {
    if (!this.hass) return;
    if (changed.has("hass") && !this._entries) {
      this._entries = [];
      listEntries(this.hass).then((e) => (this._entries = e));
    }
    const entryId = this._config?.entry_id ?? this._entries?.[0]?.entry_id;
    if (entryId && entryId !== this._roomsFor) {
      this._roomsFor = entryId;
      // One snapshot is enough to list the rooms.
      const unsub = subscribeSnapshot(this.hass, entryId, (snap) => {
        this._rooms = snap.loaded ? snap.rooms : [];
        unsub.then((u) => u());
      });
    }
  }

  render() {
    if (!this.hass || !this._config) return nothing;
    const t = this._t;
    const schema = [
      {
        name: "entry_id",
        selector: {
          select: {
            mode: "dropdown",
            options: (this._entries ?? []).map((e) => ({ value: e.entry_id, label: e.title })),
          },
        },
      },
      { name: "title", selector: { text: {} } },
      {
        name: "rooms",
        selector: {
          select: {
            multiple: true,
            mode: "list",
            options: this._rooms.map((r) => ({ value: r.id, label: r.name })),
          },
        },
      },
      {
        type: "grid",
        name: "",
        schema: [
          { name: "show_robot", selector: { boolean: {} } },
          { name: "show_outlook", selector: { boolean: {} } },
        ],
      },
    ];
    return html`<ha-form
      .hass=${this.hass}
      .data=${{ show_robot: true, show_outlook: true, ...this._config }}
      .schema=${schema}
      .computeLabel=${(field: { name: string }) => t(`card.field_${field.name}`)}
      @value-changed=${this._changed}
    ></ha-form>`;
  }

  private _changed(ev: CustomEvent<{ value: TidyRoomsCardConfig }>) {
    const config: TidyRoomsCardConfig = { ...ev.detail.value };
    for (const key of Object.keys(config) as (keyof TidyRoomsCardConfig)[]) {
      const value = config[key];
      if (value === "" || value === undefined || (Array.isArray(value) && value.length === 0))
        delete config[key];
    }
    if (config.entry_id !== this._config.entry_id) delete config.rooms;
    this.dispatchEvent(
      new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tidy-rooms-card-editor": TidyRoomsCardEditor;
  }
}
