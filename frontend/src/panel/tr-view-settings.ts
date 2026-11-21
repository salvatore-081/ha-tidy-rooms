// Settings tab: the global settings, by section, saved together.

import { element } from "../define";
import { LitElement, type PropertyValues, css, html, nothing } from "lit";
import { property, state } from "lit/decorators.js";
import { errorMessage, fetchSettingsForm, saveSettings } from "../api";
import type { FormatContext } from "../format";
import { formCallbacks, labelRobotOptions, splitErrors } from "../form";
import { notify } from "../nav";
import { shared, tokens } from "../styles";
import type { FormField, HomeAssistant, LoadedSnapshot } from "../types";

const SECTIONS: { key: string; icon: string }[] = [
  { key: "schedule", icon: "mdi:clock-outline" },
  { key: "wake", icon: "mdi:weather-sunset-up" },
  { key: "robot", icon: "mdi:robot-vacuum" },
  { key: "signals", icon: "mdi:access-point" },
];

const WORK_MODE = "work_mode_entity";
const MODE_FIELDS = ["full_mode_option", "vacuum_mode_option"];

const clean = (data: Record<string, unknown>) =>
  Object.fromEntries(
    Object.entries(data).filter(
      ([, v]) => v !== undefined && v !== "" && !(Array.isArray(v) && v.length === 0),
    ),
  );

@element("tr-view-settings")
export class TrViewSettings extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @property({ attribute: false }) snapshot!: LoadedSnapshot;
  @property({ attribute: false }) ctx!: FormatContext;
  @property({ type: Boolean }) formReady = false;

  @state() private _sections?: Record<string, FormField[]>;
  @state() private _data: Record<string, unknown> = {};
  @state() private _saved: Record<string, unknown> = {};
  @state() private _errors: Record<string, string> = {};
  @state() private _loadError?: string;
  @state() private _saving = false;
  private _loadedFor?: string;

  static styles = [
    tokens,
    shared,
    css`
      :host {
        display: grid;
        gap: var(--tr-gap);
        max-width: 760px;
        margin: 0 auto;
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
      .hint {
        margin: 6px 16px 0;
        color: var(--tr-muted);
        font-size: 0.9rem;
        line-height: 1.5;
      }
      .actions {
        position: sticky;
        bottom: 0;
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
        padding: 12px 0;
        border-top: 1px solid var(--tr-border);
        background: var(--primary-background-color, #fafafa);
      }
      .dirty {
        color: var(--tr-muted);
        font-size: 0.9rem;
      }
    `,
  ];

  protected willUpdate(changed: PropertyValues) {
    if (changed.has("hass") && this._loadedFor !== this.snapshot.entry_id && this.hass) {
      this._loadedFor = this.snapshot.entry_id;
      this._load();
    }
  }

  private async _load(workMode?: string | null) {
    try {
      const form = await fetchSettingsForm(this.hass, this.snapshot.entry_id, workMode);
      this._sections = form.sections;
      if (workMode === undefined) {
        this._data = { ...form.values };
        this._saved = { ...form.values };
      }
      this._loadError = undefined;
    } catch (err) {
      this._loadError = errorMessage(err);
    }
  }

  private get _dirty() {
    return JSON.stringify(clean(this._data)) !== JSON.stringify(clean(this._saved));
  }

  render() {
    const { t } = this.ctx;
    if (this._loadError) return html`<div class="error-box">${this._loadError}</div>`;
    if (!this._sections || !this.formReady)
      return html`<div class="card card-content muted">
        ${this.formReady || !this._sections ? t("panel.loading") : t("editor.form_unavailable")}
      </div>`;
    const cb = formCallbacks(t);
    const { base, fields } = splitErrors(this._errors);
    return html`
      ${base ? html`<div class="error-box">${cb.computeError(base)}</div>` : nothing}
      ${SECTIONS.map(({ key, icon }) => {
        let schema = this._sections![key] ?? [];
        if (key === "robot") {
          // The work mode selector lives here, before the modes it offers.
          const workMode = this._sections!.signals?.find((f) => f.name === WORK_MODE);
          schema = workMode ? [workMode, ...schema] : schema;
        }
        if (key === "signals") schema = schema.filter((f) => f.name !== WORK_MODE);
        schema = labelRobotOptions(
          schema,
          this.hass,
          this.snapshot.robot.entity_id,
          this._data[WORK_MODE] as string | undefined,
        );
        return html`<div class="card section">
          <h2><ha-icon .icon=${icon}></ha-icon>${t(`settings.section_${key}`)}</h2>
          <p class="hint">${t(`settings.hint_${key}`)}</p>
          <div class="card-content">
            ${
              schema.length
                ? html`<ha-form
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
                  ></ha-form>`
                : html`<div class="muted">${t("settings.robot_no_options")}</div>`
            }
          </div>
        </div>`;
      })}
      <div class="actions">
        <button class="btn filled" ?disabled=${this._saving || !this._dirty} @click=${this._save}>
          <ha-icon icon="mdi:content-save-outline"></ha-icon>${t("common.save")}
        </button>
        <button class="btn" ?disabled=${this._saving || !this._dirty} @click=${this._reset}>
          ${t("common.cancel")}
        </button>
        ${this._dirty ? html`<span class="dirty">${t("settings.unsaved")}</span>` : nothing}
      </div>
    `;
  }

  private _changed(ev: CustomEvent<{ value: Record<string, unknown> }>) {
    const before = this._data[WORK_MODE];
    this._data = clean({ ...this._data, ...ev.detail.value });
    for (const [k, v] of Object.entries(ev.detail.value)) if (v === undefined) delete this._data[k];
    const after = this._data[WORK_MODE];
    if (before !== after) {
      // Different selector: its options differ, so the chosen modes no longer apply.
      for (const f of MODE_FIELDS) delete this._data[f];
      this._load((after as string | undefined) ?? null);
    }
  }

  private _reset() {
    const workModeChanged = this._data[WORK_MODE] !== this._saved[WORK_MODE];
    this._data = { ...this._saved };
    this._errors = {};
    if (workModeChanged) this._load((this._saved[WORK_MODE] as string | undefined) ?? null);
  }

  private async _save() {
    const { t } = this.ctx;
    this._saving = true;
    try {
      const res = await saveSettings(this.hass, this.snapshot.entry_id, clean(this._data));
      if (res.errors) {
        this._errors = res.errors;
        return;
      }
      this._errors = {};
      this._saved = { ...clean(this._data) };
      this._data = { ...this._saved };
      notify(this, t("toast.settings_saved"));
    } catch (err) {
      this._errors = { base: errorMessage(err) };
    } finally {
      this._saving = false;
    }
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tr-view-settings": TrViewSettings;
  }
}
