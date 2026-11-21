// Overview tab: the robot, then one tile per room.

import { element } from "../define";
import { LitElement, css, html } from "lit";
import { property } from "lit/decorators.js";
import "../components/tr-robot-card";
import "../components/tr-room-tile";
import type { FormatContext } from "../format";
import { navigate, panelPath } from "../nav";
import { shared, tokens } from "../styles";
import type { HomeAssistant, LoadedSnapshot } from "../types";

@element("tr-view-overview")
export class TrViewOverview extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @property({ attribute: false }) snapshot!: LoadedSnapshot;
  @property({ attribute: false }) ctx!: FormatContext;
  @property({ type: Boolean }) narrow = false;

  static styles = [
    tokens,
    shared,
    css`
      :host {
        display: grid;
        gap: var(--tr-gap);
      }
      .rooms {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
        gap: var(--tr-gap);
      }
      .note {
        font-size: 0.85rem;
        font-weight: 400;
      }
      @media (max-width: 600px) {
        .section-title .spacer {
          flex-basis: 100%;
        }
        :host,
        .rooms {
          gap: 12px;
        }
        .rooms {
          grid-template-columns: 1fr;
        }
      }
      .section-title {
        display: flex;
        flex-wrap: wrap;
        align-items: baseline;
        gap: 2px 8px;
        margin: 8px 4px -4px;
        font-size: 1rem;
        font-weight: 500;
        color: var(--tr-muted);
      }
    `,
  ];

  render() {
    const s = this.snapshot;
    const { t } = this.ctx;
    const admin = this.hass.user?.is_admin ?? true;
    return html`
      <tr-robot-card
        .hass=${this.hass}
        .snapshot=${s}
        .ctx=${this.ctx}
        .admin=${admin}
      ></tr-robot-card>
      ${
        s.rooms.length
          ? html`
              <div class="section-title">
                <span class="spacer">${t("overview.rooms", { n: s.rooms.length })}</span>
                <span class="note">${t("overview.estimate_note")}</span>
              </div>
              <div class="rooms">
                ${s.rooms.map(
                  (room) =>
                    html`<tr-room-tile
                      .hass=${this.hass}
                      .snapshot=${s}
                      .room=${room}
                      .ctx=${this.ctx}
                      .admin=${admin}
                      .next=${room.id === s.next_room && !s.job && s.enabled}
                    ></tr-room-tile>`,
                )}
              </div>
            `
          : html`<div class="card empty-state">
              <ha-icon icon="mdi:floor-plan"></ha-icon>
              <p>${t("overview.no_rooms")}</p>
              <button class="btn filled" @click=${() => navigate(panelPath("/rooms/new"))}>
                <ha-icon icon="mdi:plus"></ha-icon>${t("rooms.add")}
              </button>
            </div>`
      }
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tr-view-overview": TrViewOverview;
  }
}
