// The robot: state, battery, automatic cleaning, current job and what comes next.

import { element } from "../define";
import { LitElement, css, html, nothing } from "lit";
import { property } from "lit/decorators.js";
import "./tr-switch";
import { callAction, errorMessage } from "../api";
import { notify } from "../nav";
import {
  type FormatContext,
  formatClock,
  formatDuration,
  formatTime,
  outlookText,
} from "../format";
import { shared, tokens } from "../styles";
import type { HomeAssistant, LoadedSnapshot } from "../types";

// VacuumEntityFeature
const RETURN_HOME = 16;
const LOCATE = 512;

/** A button's name without the robot's name in front ("Tatiana Lava il mocio" → "Lava il mocio"). */
export const buttonName = (friendly: string, robot: string): string => {
  const rest = friendly.startsWith(`${robot} `) ? friendly.slice(robot.length + 1) : friendly;
  return rest ? rest.charAt(0).toUpperCase() + rest.slice(1) : friendly;
};

const batteryIcon = (level: number | null): string => {
  if (level === null) return "mdi:battery-unknown";
  const step = Math.round(level / 10) * 10;
  if (step >= 100) return "mdi:battery";
  if (step <= 0) return "mdi:battery-outline";
  return `mdi:battery-${step}`;
};

@element("tr-robot-card")
export class TrRobotCard extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @property({ attribute: false }) snapshot!: LoadedSnapshot;
  @property({ attribute: false }) ctx!: FormatContext;
  @property({ type: Boolean }) admin = false;

  static styles = [
    tokens,
    shared,
    css`
      :host {
        display: block;
      }
      .top {
        display: flex;
        align-items: center;
        gap: 16px;
        padding: 16px;
      }
      .avatar {
        flex: none;
        display: flex;
        align-items: center;
        justify-content: center;
        width: 48px;
        height: 48px;
        border-radius: 50%;
        color: var(--tone);
        background: color-mix(in srgb, var(--tone) 14%, transparent);
      }
      .avatar ha-icon {
        --mdc-icon-size: 28px;
      }
      .name {
        font-size: 1.15rem;
        font-weight: 500;
      }
      .sub {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 4px 12px;
        color: var(--tr-muted);
        font-size: 0.9rem;
        margin-top: 2px;
      }
      .sub ha-icon {
        --mdc-icon-size: 18px;
        vertical-align: -3px;
      }
      .auto {
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 0.9rem;
      }
      .actions {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        padding: 0 16px 14px;
      }
      .actions .btn ha-icon,
      .actions .btn ha-state-icon {
        --mdc-icon-size: 18px;
      }
      .lines {
        border-top: 1px solid var(--tr-border);
        padding: 4px 16px;
      }
      .line {
        display: flex;
        align-items: center;
        gap: 12px;
        min-height: 44px;
        padding: 6px 0;
      }
      .line + .line {
        border-top: 1px solid var(--tr-border);
      }
      .line > ha-icon {
        color: var(--tr-muted);
        flex: none;
      }
      .line .text {
        flex: 1;
        min-width: 0;
      }
      .line .secondary {
        color: var(--tr-muted);
        font-size: 0.85rem;
      }
      @media (max-width: 600px) {
        .top {
          flex-wrap: wrap;
        }
        .auto {
          width: 100%;
          justify-content: space-between;
        }
      }
    `,
  ];

  render() {
    const s = this.snapshot;
    const { t } = this.ctx;
    const robot = s.robot;
    const stateObj = this.hass.states[robot.entity_id];
    const stateText =
      stateObj && this.hass.formatEntityState
        ? this.hass.formatEntityState(stateObj)
        : (robot.state ?? t("robot.unknown"));
    const tone = !robot.available
      ? "tone-error"
      : s.job
        ? "tone-active"
        : s.enabled
          ? "tone-ready"
          : "tone-off";
    return html`
      <div class="card">
        <div class="top">
          <div class="avatar ${tone}">
            <ha-icon
              icon=${robot.available ? "mdi:robot-vacuum" : "mdi:robot-vacuum-off"}
            ></ha-icon>
          </div>
          <div class="spacer">
            <div class="name">${robot.name}</div>
            <div class="sub">
              <span>${stateText}</span>
              ${
                robot.battery !== null
                  ? html`<span
                      ><ha-icon .icon=${batteryIcon(robot.battery)}></ha-icon>
                      ${robot.battery}%</span
                    >`
                  : nothing
              }
            </div>
          </div>
          <div class="auto">
            <span>${t("robot.automatic")}</span>
            <tr-switch
              .checked=${s.enabled}
              .disabled=${!this.admin}
              .label=${t("robot.automatic")}
              @change=${this._toggle}
            ></tr-switch>
          </div>
        </div>
        ${this.admin ? this._actions() : nothing}
        <div class="lines">${this._job()} ${this._next()} ${this._schedule()}</div>
      </div>
    `;
  }

  private _job() {
    const s = this.snapshot;
    const { t } = this.ctx;
    if (!s.job) {
      return html`<div class="line">
        <ha-icon icon="mdi:sleep"></ha-icon>
        <div class="text">
          ${s.enabled ? t("robot.no_job") : t("robot.paused")}
          ${
            s.paused_until
              ? html`<div class="secondary">
                  ${t("wait.robot_paused", { time: formatTime(s.paused_until, this.ctx) })}
                </div>`
              : nothing
          }
        </div>
      </div>`;
    }
    const job = s.job;
    const elapsed = formatDuration(this.ctx.now.getTime() - new Date(job.created).getTime(), t);
    const flags = [
      job.manual ? t("job.manual") : job.forced ? t("job.forced") : "",
      job.manual && job.pass_id === null ? t("job.not_counted") : "",
      job.quiet ? t("job.quiet") : "",
      job.attempts > 1 ? t("job.attempts", { n: job.attempts }) : "",
    ].filter(Boolean);
    return html`<div class="line">
      <ha-icon icon="mdi:robot-vacuum"></ha-icon>
      <div class="text">
        ${t("job.title", { mode: this.ctx.mode(job.work_mode), room: job.room })}
        <div class="secondary">
          ${t(`job.phase_${job.phase}`)} · ${t("job.since", { duration: elapsed })}
          ${flags.length ? html` · ${flags.join(" · ")}` : nothing}
        </div>
      </div>
      ${
        this.admin
          ? html`<button class="btn danger" @click=${this._stop}>
              <ha-icon icon="mdi:home-import-outline"></ha-icon>${t("job.stop")}
            </button>`
          : nothing
      }
    </div>`;
  }

  private _next() {
    const s = this.snapshot;
    const { t } = this.ctx;
    if (!s.enabled) return nothing;
    const room = s.rooms.find((r) => r.id === s.next_room);
    if (!room || s.job?.room_id === room.id) {
      const allDone =
        s.rooms.length > 0 && s.rooms.every((r) => !r.enabled || r.outlook.pass_id === null);
      return s.rooms.length && !s.job
        ? html`<div class="line">
            <ha-icon icon=${allDone ? "mdi:check-all" : "mdi:calendar-clock"}></ha-icon>
            <div class="text">${allDone ? t("robot.all_done") : t("robot.nothing_planned")}</div>
          </div>`
        : nothing;
    }
    return html`<div class="line">
      <ha-icon icon="mdi:calendar-arrow-right"></ha-icon>
      <div class="text">
        ${t("robot.next", { room: room.name })}
        <div class="secondary">${outlookText(room, this.ctx)} · ${t("robot.estimate")}</div>
      </div>
    </div>`;
  }

  private _schedule() {
    const s = this.snapshot;
    const { t } = this.ctx;
    const parts: string[] = [];
    if (s.quiet_start && s.quiet_end)
      parts.push(
        t("robot.quiet_hours", {
          start: formatClock(s.quiet_start, this.ctx),
          end: formatClock(s.quiet_end, this.ctx),
        }),
      );
    if (s.wake_check_today) parts.push(s.awake ? t("robot.awake") : t("robot.not_awake"));
    parts.push(t("robot.min_battery", { n: s.min_battery }));
    return html`<div class="line">
      <ha-icon icon="mdi:clock-outline"></ha-icon>
      <div class="text secondary">${parts.join(" · ")}</div>
    </div>`;
  }

  /** The robot's own commands: back to the dock, locate, and the buttons of its device. */
  private _actions() {
    const { t } = this.ctx;
    const robot = this.snapshot.robot;
    const off = !robot.available;
    const buttons = robot.buttons
      .map((id) => this.hass.states[id])
      .filter((st) => st !== undefined);
    const home = Boolean(robot.features & RETURN_HOME);
    const locate = Boolean(robot.features & LOCATE);
    if (!home && !locate && !buttons.length) return nothing;
    return html`<div class="actions" role="group" aria-label=${t("robot.actions")}>
      ${
        home
          ? html`<button class="btn" ?disabled=${off} @click=${this._home}>
              <ha-icon icon="mdi:home-import-outline"></ha-icon>${t("robot.return_home")}
            </button>`
          : nothing
      }
      ${
        locate
          ? html`<button
              class="btn"
              ?disabled=${off}
              @click=${() => this._call("vacuum", "locate", robot.entity_id, t("robot.locate"))}
            >
              <ha-icon icon="mdi:map-marker-radius-outline"></ha-icon>${t("robot.locate")}
            </button>`
          : nothing
      }
      ${buttons.map((st) => {
        const name = buttonName(String(st.attributes.friendly_name ?? st.entity_id), robot.name);
        return html`<button
          class="btn"
          ?disabled=${off || st.state === "unavailable"}
          @click=${() => this._call("button", "press", st.entity_id, name)}
        >
          <ha-state-icon .hass=${this.hass} .stateObj=${st}></ha-state-icon>${name}
        </button>`;
      })}
    </div>`;
  }

  private _home() {
    // A job of Tidy Rooms is stopped through it, so it does not count as done.
    if (this.snapshot.job) {
      this._stop();
      return;
    }
    const robot = this.snapshot.robot;
    this._call("vacuum", "return_to_base", robot.entity_id, this.ctx.t("robot.return_home"));
  }

  private async _call(domain: string, service: string, entityId: string, label: string) {
    try {
      await callAction(this.hass, domain, service, entityId);
      notify(this, this.ctx.t("robot.sent", { action: label }));
    } catch (err) {
      notify(this, errorMessage(err));
    }
  }

  private _toggle(ev: CustomEvent<{ checked: boolean }>) {
    this.dispatchEvent(
      new CustomEvent("set-enabled", {
        detail: { enabled: ev.detail.checked },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _stop() {
    this.dispatchEvent(new CustomEvent("stop-job", { bubbles: true, composed: true }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tr-robot-card": TrRobotCard;
  }
}
