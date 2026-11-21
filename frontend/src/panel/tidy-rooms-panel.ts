// The sidebar panel: toolbar, tabs and routing; it owns the live snapshot.

import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import "../components/tr-confirm";
import "./tr-view-overview";
import "./tr-view-rooms";
import "./tr-room-editor";
import "./tr-view-history";
import "./tr-view-settings";
import {
  cleanNow,
  errorCode,
  errorMessage,
  listEntries,
  setEnabled,
  stopJob,
  subscribeSnapshot,
} from "../api";
import { confirmDialog } from "../components/tr-confirm";
import { type FormatContext, formatContext } from "../format";
import { loadHaForm } from "../load-ha-elements";
import { type Localize, localizer } from "../localize";
import { BASE, navigate, notify, panelPath } from "../nav";
import { shared, tokens } from "../styles";
import type { CleanKind, EntrySummary, HomeAssistant, LoadedSnapshot, Snapshot } from "../types";

type Tab = "overview" | "rooms" | "history" | "settings";
const TABS: Tab[] = ["overview", "rooms", "history", "settings"];
const TICK_MS = 30_000;

@customElement("tidy-rooms-panel")
export class TidyRoomsPanel extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @property({ type: Boolean, reflect: true }) narrow = false;
  @property({ attribute: false }) route?: { prefix: string; path: string };

  @state() private _entries?: EntrySummary[];
  @state() private _entryId?: string;
  @state() private _snapshot?: Snapshot;
  @state() private _error?: string;
  @state() private _formReady = false;
  @state() private _now = new Date();

  private _unsub?: Promise<() => void>;
  private _subscribedTo?: string;
  private _timer?: number;

  static styles = [
    tokens,
    shared,
    css`
      :host {
        display: block;
        min-height: 100vh;
        background: var(--primary-background-color, #fafafa);
        color: var(--tr-text);
        font-family: var(--paper-font-body1_-_font-family, inherit);
      }
      .toolbar {
        position: sticky;
        top: 0;
        z-index: 4;
        background: var(--app-header-background-color, var(--primary-color));
        color: var(--app-header-text-color, var(--text-primary-color, #fff));
        border-bottom: var(--app-header-border-bottom, none);
        padding-top: env(safe-area-inset-top);
      }
      .bar {
        display: flex;
        align-items: center;
        gap: 4px;
        height: var(--header-height, 56px);
        padding: 0 12px 0 4px;
        box-sizing: border-box;
      }
      .bar .title {
        flex: 1;
        font-size: 20px;
        font-weight: 400;
        margin-left: 12px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .bar select {
        font: inherit;
        color: inherit;
        background: transparent;
        border: 1px solid currentColor;
        border-radius: 8px;
        padding: 4px 8px;
        max-width: 45vw;
      }
      .bar select option {
        color: var(--tr-text);
        background: var(--tr-card-bg);
      }
      nav {
        display: flex;
        gap: 4px;
        padding: 0 8px;
        overflow-x: auto;
        scrollbar-width: none;
      }
      .tab {
        position: relative;
        padding: 0 16px;
        height: 48px;
        display: inline-flex;
        align-items: center;
        gap: 8px;
        color: inherit;
        opacity: 0.75;
        text-decoration: none;
        font-weight: 500;
        font-size: 0.95rem;
        white-space: nowrap;
        border-radius: 8px 8px 0 0;
      }
      .tab ha-icon {
        --mdc-icon-size: 20px;
      }
      .tab[aria-current="page"] {
        opacity: 1;
      }
      .tab[aria-current="page"]::after {
        content: "";
        position: absolute;
        left: 12px;
        right: 12px;
        bottom: 0;
        height: 3px;
        border-radius: 3px 3px 0 0;
        background: currentColor;
      }
      main {
        max-width: 1280px;
        margin: 0 auto;
        padding: var(--tr-gap);
        box-sizing: border-box;
      }
      :host([narrow]) main {
        padding: 12px;
      }
      :host([narrow]) .tab span {
        display: none;
      }
      :host([narrow]) .tab {
        flex: 1;
        justify-content: center;
      }
      .center {
        display: flex;
        justify-content: center;
        padding: 64px 16px;
        color: var(--tr-muted);
      }
    `,
  ];

  private get _t(): Localize {
    return localizer(this.hass?.locale?.language || this.hass?.language);
  }

  private get _ctx(): FormatContext {
    return formatContext(this.hass, this._t, this._now);
  }

  connectedCallback() {
    super.connectedCallback();
    this._timer = window.setInterval(() => (this._now = new Date()), TICK_MS);
    if (this.hass) this._subscribe();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    window.clearInterval(this._timer);
    this._unsubscribe();
  }

  protected firstUpdated() {
    loadHaForm().then((ok) => (this._formReady = ok));
    this._loadEntries();
  }

  protected updated(changed: Map<string, unknown>) {
    if (changed.has("_entryId") || (changed.has("hass") && !this._unsub)) this._subscribe();
  }

  private async _loadEntries() {
    try {
      const entries = await listEntries(this.hass);
      this._entries = entries;
      const wanted = new URLSearchParams(location.search).get("entry");
      this._entryId =
        entries.find((e) => e.entry_id === wanted)?.entry_id ?? entries[0]?.entry_id ?? undefined;
    } catch (err) {
      this._error = errorMessage(err);
    }
  }

  private _subscribe() {
    if (!this.hass || !this._entryId || this._subscribedTo === this._entryId) return;
    this._unsubscribe();
    const entryId = this._entryId;
    this._subscribedTo = entryId;
    this._snapshot = undefined;
    this._unsub = subscribeSnapshot(this.hass, entryId, (snap) => {
      if (this._subscribedTo === entryId) {
        this._snapshot = snap;
        this._now = new Date();
      }
    });
    this._unsub.catch((err) => (this._error = errorMessage(err)));
  }

  private _unsubscribe() {
    this._unsub?.then((unsub) => unsub()).catch(() => undefined);
    this._unsub = undefined;
    this._subscribedTo = undefined;
  }

  private get _segments(): string[] {
    return (this.route?.path ?? "").split("/").filter(Boolean);
  }

  private get _tab(): Tab {
    const first = this._segments[0] as Tab | undefined;
    return first && TABS.includes(first) ? first : "overview";
  }

  render() {
    const t = this._t;
    return html`
      <div class="toolbar">
        <div class="bar">
          <ha-menu-button .hass=${this.hass} .narrow=${this.narrow}></ha-menu-button>
          <div class="title">Tidy Rooms</div>
          ${
            this._entries && this._entries.length > 1
              ? html`<select aria-label=${t("panel.robot")} @change=${this._pickEntry}>
                  ${this._entries.map(
                    (e) =>
                      html`<option value=${e.entry_id} ?selected=${e.entry_id === this._entryId}>
                        ${e.title}
                      </option>`,
                  )}
                </select>`
              : nothing
          }
        </div>
        <nav aria-label="Tidy Rooms">
          ${TABS.map(
            (tab) =>
              html`<a
                class="tab"
                href=${tab === "overview" ? BASE : `${BASE}/${tab}`}
                aria-current=${this._tab === tab ? "page" : "false"}
                @click=${(ev: MouseEvent) => this._goTab(ev, tab)}
              >
                <ha-icon .icon=${TAB_ICONS[tab]}></ha-icon><span>${t(`tab.${tab}`)}</span>
              </a>`,
          )}
        </nav>
      </div>
      <main>${this._content()}</main>
    `;
  }

  private _content() {
    const t = this._t;
    if (this._error) return html`<div class="error-box">${this._error}</div>`;
    if (this._entries && this._entries.length === 0)
      return html`<div class="card empty-state">
        <ha-icon icon="mdi:robot-vacuum"></ha-icon>${t("panel.no_entries")}
      </div>`;
    const snap = this._snapshot;
    if (!snap) return html`<div class="center">${t("panel.loading")}</div>`;
    if (!snap.loaded) return html`<div class="center">${t("panel.not_loaded")}</div>`;
    const common = {
      hass: this.hass,
      snapshot: snap,
      ctx: this._ctx,
    };
    switch (this._tab) {
      case "overview":
        return html`<tr-view-overview
          .hass=${common.hass}
          .snapshot=${snap}
          .ctx=${common.ctx}
          .narrow=${this.narrow}
          @set-enabled=${this._setEnabled}
          @stop-job=${this._stopJob}
          @clean-now=${this._cleanNow}
          @open-room=${this._openRoom}
        ></tr-view-overview>`;
      case "rooms": {
        const id = this._segments[1];
        if (id)
          return html`<tr-room-editor
            .hass=${common.hass}
            .snapshot=${snap}
            .ctx=${common.ctx}
            .roomId=${id === "new" ? undefined : id}
            .formReady=${this._formReady}
            @clean-now=${this._cleanNow}
          ></tr-room-editor>`;
        return html`<tr-view-rooms
          .hass=${common.hass}
          .snapshot=${snap}
          .ctx=${common.ctx}
        ></tr-view-rooms>`;
      }
      case "history":
        return html`<tr-view-history
          .hass=${common.hass}
          .snapshot=${snap}
          .ctx=${common.ctx}
          .narrow=${this.narrow}
        ></tr-view-history>`;
      case "settings":
        return html`<tr-view-settings
          .hass=${common.hass}
          .snapshot=${snap}
          .ctx=${common.ctx}
          .formReady=${this._formReady}
        ></tr-view-settings>`;
    }
  }

  private _goTab(ev: MouseEvent, tab: Tab) {
    if (ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.button !== 0) return;
    ev.preventDefault();
    navigate(panelPath(tab === "overview" ? "" : `/${tab}`));
  }

  private _pickEntry(ev: Event) {
    this._entryId = (ev.target as HTMLSelectElement).value;
    const url = new URL(location.href);
    url.searchParams.set("entry", this._entryId);
    navigate(url.pathname + url.search, true);
  }

  private get _loaded(): LoadedSnapshot | undefined {
    return this._snapshot?.loaded ? this._snapshot : undefined;
  }

  private async _setEnabled(ev: CustomEvent<{ enabled: boolean }>) {
    const snap = this._loaded;
    if (!snap) return;
    try {
      await setEnabled(this.hass, snap.entry_id, ev.detail.enabled);
    } catch (err) {
      notify(this, errorMessage(err));
    }
  }

  private async _stopJob() {
    const snap = this._loaded;
    if (!snap?.job) return;
    const t = this._t;
    const ok = await confirmDialog(this.renderRoot as ShadowRoot, {
      title: t("confirm.stop_title"),
      text: t("confirm.stop_text", { room: snap.job.room }),
      confirm: t("job.stop"),
      cancel: t("common.cancel"),
      destructive: true,
    });
    if (!ok) return;
    try {
      await stopJob(this.hass, snap.entry_id);
    } catch (err) {
      notify(this, errorMessage(err));
    }
  }

  private async _cleanNow(ev: CustomEvent<{ room: string; kind: CleanKind }>) {
    const snap = this._loaded;
    const room = snap?.rooms.find((r) => r.id === ev.detail.room);
    if (!snap || !room) return;
    const t = this._t;
    const ok = await confirmDialog(this.renderRoot as ShadowRoot, {
      title: t(`confirm.clean_title_${ev.detail.kind}`, { room: room.name }),
      text: t("confirm.clean_text"),
      confirm: t("confirm.clean_confirm"),
      cancel: t("common.cancel"),
    });
    if (!ok) return;
    try {
      await cleanNow(this.hass, snap.entry_id, room.id, ev.detail.kind);
      notify(this, t("toast.clean_started", { room: room.name }));
    } catch (err) {
      notify(this, errorCode(err) === "robot_busy" ? t("error.robot_busy") : errorMessage(err));
    }
  }

  private _openRoom(ev: CustomEvent<{ room: string }>) {
    navigate(panelPath(`/rooms/${ev.detail.room}`));
  }
}

const TAB_ICONS: Record<Tab, string> = {
  overview: "mdi:view-dashboard-outline",
  rooms: "mdi:floor-plan",
  history: "mdi:history",
  settings: "mdi:cog-outline",
};

declare global {
  interface HTMLElementTagNameMap {
    "tidy-rooms-panel": TidyRoomsPanel;
  }
}
