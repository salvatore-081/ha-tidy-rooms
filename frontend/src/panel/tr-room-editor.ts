// A room: its live status and recent jobs, and the form to add or edit it.

import { LitElement, type PropertyValues, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import "../components/tr-room-tile";
import { deleteRoom, errorMessage, fetchHistory, fetchRoomForm, saveRoom } from "../api";
import { confirmDialog } from "../components/tr-confirm";
import { type FormatContext, formatDayTime, formatDuration } from "../format";
import { formCallbacks, splitErrors } from "../form";
import { navigate, notify, panelPath } from "../nav";
import { shared, tokens } from "../styles";
import type { FormField, HomeAssistant, JobRecord, LoadedSnapshot } from "../types";

// Sections of the form, by field name (fields not listed go to the last one).
const SECTIONS: { key: string; icon: string; fields: string[] }[] = [
  { key: "area", icon: "mdi:floor-plan", fields: ["area"] },
  {
    key: "presence",
    icon: "mdi:motion-sensor",
    fields: ["occupancy_sensors", "proxy_sensors", "empty_minutes"],
  },
  {
    key: "targets",
    icon: "mdi:target",
    fields: ["full_per_day", "vacuum_per_day", "min_gap_hours"],
  },
  {
    key: "deadlines",
    icon: "mdi:clock-alert-outline",
    fields: ["full_deadline", "vacuum_deadline"],
  },
  { key: "advanced", icon: "mdi:code-braces", fields: [] },
];

@customElement("tr-room-editor")
export class TrRoomEditor extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @property({ attribute: false }) snapshot!: LoadedSnapshot;
  @property({ attribute: false }) ctx!: FormatContext;
  @property({ attribute: false }) roomId?: string;
  @property({ type: Boolean }) formReady = false;

  @state() private _schema?: FormField[];
  @state() private _data: Record<string, unknown> = {};
  @state() private _errors: Record<string, string> = {};
  @state() private _loadError?: string;
  @state() private _saving = false;
  @state() private _jobs?: JobRecord[];
  private _loadedFor?: string;

  static styles = [
    tokens,
    shared,
    css`
      :host {
        display: block;
        max-width: 1100px;
        margin: 0 auto;
      }
      .header {
        display: flex;
        align-items: center;
        gap: 8px;
        margin: 0 0 16px;
      }
      .header h1 {
        flex: 1;
        margin: 0;
        font-size: 1.5rem;
        font-weight: 400;
      }
      .layout {
        display: grid;
        grid-template-columns: minmax(0, 1fr) 340px;
        gap: var(--tr-gap);
        align-items: start;
      }
      .layout.new {
        grid-template-columns: minmax(0, 720px);
        justify-content: center;
      }
      .side {
        display: grid;
        gap: var(--tr-gap);
      }
      .forms {
        display: grid;
        gap: var(--tr-gap);
      }
      .section h2 {
        display: flex;
        align-items: center;
        gap: 10px;
        margin: 0;
        padding: 16px 16px 0;
        font-size: 1rem;
        font-weight: 500;
      }
      .section h2 ha-icon {
        color: var(--tr-muted);
      }
      .section .card-content {
        padding-top: 8px;
      }
      .hint {
        margin: 4px 0 0;
        color: var(--tr-muted);
        font-size: 0.9rem;
        line-height: 1.5;
      }
      details summary {
        cursor: pointer;
        list-style: none;
      }
      details summary::-webkit-details-marker {
        display: none;
      }
      details summary h2::after {
        content: "";
        margin-left: auto;
        width: 8px;
        height: 8px;
        border-right: 2px solid var(--tr-muted);
        border-bottom: 2px solid var(--tr-muted);
        transform: rotate(45deg);
      }
      details[open] summary h2::after {
        transform: rotate(-135deg);
      }
      details:not([open]) summary h2 {
        padding-bottom: 16px;
      }
      .actions {
        position: sticky;
        bottom: 0;
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        padding: 12px 0;
        background: var(--primary-background-color, #fafafa);
      }
      .jobs h2 {
        margin: 0;
        padding: 16px 16px 4px;
        font-size: 1rem;
        font-weight: 500;
      }
      .job {
        display: flex;
        gap: 12px;
        align-items: center;
        padding: 8px 16px;
        font-size: 0.9rem;
      }
      .job + .job {
        border-top: 1px solid var(--tr-border);
      }
      .job ha-icon {
        --mdc-icon-size: 20px;
        color: var(--tr-muted);
      }
      .job .when {
        flex: 1;
      }
      .job .secondary {
        color: var(--tr-muted);
        font-size: 0.8rem;
      }
      .jobs .empty {
        padding: 8px 16px 16px;
        color: var(--tr-muted);
        font-size: 0.9rem;
      }
      @media (max-width: 900px) {
        .layout {
          grid-template-columns: minmax(0, 1fr);
        }
        .side {
          order: -1;
        }
      }
    `,
  ];

  protected willUpdate(changed: PropertyValues) {
    const key = this.roomId ?? "new";
    if ((changed.has("roomId") || changed.has("hass")) && this._loadedFor !== key && this.hass) {
      this._loadedFor = key;
      this._load();
    }
  }

  private async _load() {
    this._schema = undefined;
    this._errors = {};
    this._loadError = undefined;
    this._jobs = undefined;
    try {
      const form = await fetchRoomForm(this.hass, this.snapshot.entry_id, this.roomId);
      this._schema = form.schema;
      this._data = { ...form.values };
    } catch (err) {
      this._loadError = errorMessage(err);
    }
    if (this.roomId) {
      try {
        const history = await fetchHistory(this.hass, this.snapshot.entry_id, 30, this.roomId);
        this._jobs = history.jobs.slice(0, 8);
      } catch {
        this._jobs = [];
      }
    }
  }

  render() {
    const { t } = this.ctx;
    const room = this.roomId ? this.snapshot.rooms.find((r) => r.id === this.roomId) : undefined;
    const title = this.roomId ? (room?.name ?? t("editor.unknown")) : t("editor.new_title");
    return html`
      <div class="header">
        <button
          class="icon-btn"
          aria-label=${t("common.back")}
          title=${t("common.back")}
          @click=${this._back}
        >
          <ha-icon icon="mdi:arrow-left"></ha-icon>
        </button>
        <h1>${title}</h1>
      </div>
      ${
        this.roomId && !room && !this._schema && this._loadError
          ? html`<div class="error-box">${t("editor.not_found")}</div>`
          : html`<div class="layout ${room ? "" : "new"}">
              <div class="forms">${this._form()}</div>
              ${
                room
                  ? html`<div class="side">
                      <tr-room-tile
                        .hass=${this.hass}
                        .snapshot=${this.snapshot}
                        .room=${room}
                        .ctx=${this.ctx}
                        .admin=${true}
                      ></tr-room-tile>
                      ${this._jobsCard()}
                    </div>`
                  : nothing
              }
            </div>`
      }
    `;
  }

  private _form() {
    const { t } = this.ctx;
    if (this._loadError) return html`<div class="error-box">${this._loadError}</div>`;
    if (!this._schema || !this.formReady)
      return html`<div class="card card-content muted">
        ${this.formReady || !this._schema ? t("panel.loading") : t("editor.form_unavailable")}
      </div>`;
    const cb = formCallbacks(t);
    const { base, fields } = splitErrors(this._errors);
    const listed = new Set(SECTIONS.flatMap((s) => s.fields));
    return html`
      ${base ? html`<div class="error-box">${cb.computeError(base)}</div>` : nothing}
      ${SECTIONS.map((section) => {
        const schema = this._schema!.filter((f) =>
          section.fields.length ? section.fields.includes(f.name) : !listed.has(f.name),
        );
        if (!schema.length) return nothing;
        const form = html`<div class="card-content">
          <ha-form
            .hass=${this.hass}
            .data=${this._data}
            .schema=${schema}
            .error=${fields}
            .computeLabel=${cb.computeLabel}
            .computeHelper=${cb.computeHelper}
            .computeError=${cb.computeError}
            .localizeValue=${cb.localizeValue}
            .disabled=${this._saving}
            @value-changed=${this._changed}
          ></ha-form>
        </div>`;
        const heading = html`<h2>
          <ha-icon .icon=${section.icon}></ha-icon>${t(`editor.section_${section.key}`)}
        </h2>`;
        if (section.key === "advanced")
          return html`<details class="card section" ?open=${Boolean(this._data.clean_action)}>
            <summary>${heading}</summary>
            <div class="card-content hint">${t("editor.advanced_hint")}</div>
            ${form}
          </details>`;
        return html`<div class="card section">
          ${heading}
          ${
            section.key === "area"
              ? html`<div class="card-content hint">${t("editor.area_hint")}</div>`
              : nothing
          }
          ${form}
        </div>`;
      })}
      <div class="actions">
        <button class="btn filled" ?disabled=${this._saving} @click=${this._save}>
          <ha-icon icon="mdi:content-save-outline"></ha-icon>${t("common.save")}
        </button>
        <button class="btn" ?disabled=${this._saving} @click=${this._back}>
          ${t("common.cancel")}
        </button>
        <span class="spacer"></span>
        ${
          this.roomId
            ? html`<button class="btn danger" ?disabled=${this._saving} @click=${this._delete}>
                <ha-icon icon="mdi:delete-outline"></ha-icon>${t("common.delete")}
              </button>`
            : nothing
        }
      </div>
    `;
  }

  private _jobsCard() {
    const { t } = this.ctx;
    return html`<div class="card jobs">
      <h2>${t("editor.recent_jobs")}</h2>
      ${
        this._jobs === undefined
          ? html`<div class="empty">${t("panel.loading")}</div>`
          : this._jobs.length === 0
            ? html`<div class="empty">${t("history.empty")}</div>`
            : this._jobs.map((job) => {
                const duration = formatDuration(
                  new Date(job.ended).getTime() - new Date(job.started).getTime(),
                  t,
                );
                return html`<div class="job">
                  <ha-icon icon=${job.kind === "full" ? "mdi:water" : "mdi:broom"}></ha-icon>
                  <div class="when">
                    ${formatDayTime(job.started, this.ctx)}
                    <div class="secondary">${t(`kind.${job.kind}`)} · ${duration}</div>
                  </div>
                  <span class="chip tone-${RESULT_TONE[job.result]}"
                    >${t(`result.${job.result}`)}</span
                  >
                </div>`;
              })
      }
    </div>`;
  }

  private _changed(ev: CustomEvent<{ value: Record<string, unknown> }>) {
    this._data = { ...this._data, ...ev.detail.value };
    for (const [key, value] of Object.entries(ev.detail.value))
      if (value === undefined || value === "" || (Array.isArray(value) && value.length === 0))
        delete this._data[key];
  }

  private async _save() {
    const { t } = this.ctx;
    this._saving = true;
    try {
      const res = await saveRoom(this.hass, this.snapshot.entry_id, this._data, this.roomId);
      if (res.errors) {
        this._errors = res.errors;
        return;
      }
      notify(this, t(this.roomId ? "toast.room_saved" : "toast.room_added"));
      navigate(panelPath("/rooms"));
    } catch (err) {
      this._errors = { base: errorMessage(err) };
    } finally {
      this._saving = false;
    }
  }

  private async _delete() {
    const { t } = this.ctx;
    const room = this.snapshot.rooms.find((r) => r.id === this.roomId);
    if (!this.roomId) return;
    const ok = await confirmDialog(this.renderRoot as ShadowRoot, {
      title: t("confirm.delete_title", { room: room?.name ?? "" }),
      text: t("confirm.delete_text"),
      confirm: t("common.delete"),
      cancel: t("common.cancel"),
      destructive: true,
    });
    if (!ok) return;
    try {
      await deleteRoom(this.hass, this.snapshot.entry_id, this.roomId);
      notify(this, t("toast.room_deleted", { room: room?.name ?? "" }));
      navigate(panelPath("/rooms"), true);
    } catch (err) {
      notify(this, errorMessage(err));
    }
  }

  private _back() {
    navigate(panelPath("/rooms"));
  }
}

export const RESULT_TONE: Record<string, string> = {
  done: "success",
  interrupted: "warning",
  failed: "error",
  stopped: "waiting",
};

declare global {
  interface HTMLElementTagNameMap {
    "tr-room-editor": TrRoomEditor;
  }
}
