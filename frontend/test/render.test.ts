import { describe, expect, it } from "vitest";
import "../src/components/tr-room-tile";
import "../src/components/tr-robot-card";
import { formatContext } from "../src/format";
import { localizer } from "../src/localize";
import { NOW, hass, room, snapshot } from "./fixtures";

const ctx = formatContext(hass("en"), localizer("en"), NOW);

const mount = async <T extends HTMLElement & { updateComplete: Promise<boolean> }>(el: T) => {
  document.body.appendChild(el);
  await el.updateComplete;
  return el.shadowRoot!;
};

describe("room tile", () => {
  it("shows status, explanation and buttons for admins", async () => {
    const el = document.createElement("tr-room-tile");
    Object.assign(el, {
      hass: hass("en"),
      snapshot: snapshot(),
      room: room(),
      ctx,
      admin: true,
      next: true,
    });
    const root = await mount(el);
    const text = root.textContent!.replace(/\s+/g, " ");
    expect(text).toContain("Cucina");
    expect(text).toContain("Waiting for the room to be empty");
    expect(text).toContain("Empty for 4 of 10 min");
    expect(text).toContain("Next");
    expect(root.querySelectorAll(".actions .btn")).toHaveLength(2);
  });

  it("emits clean-now with the kind", async () => {
    const el = document.createElement("tr-room-tile");
    Object.assign(el, { hass: hass("en"), snapshot: snapshot(), room: room(), ctx, admin: true });
    const root = await mount(el);
    let detail: unknown;
    el.addEventListener("clean-now", (ev) => (detail = (ev as CustomEvent).detail));
    (root.querySelectorAll(".actions .btn")[1] as HTMLButtonElement).click();
    expect(detail).toEqual({ room: "kitchen", kind: "vacuum" });
  });

  it("disables the buttons while the robot is busy", async () => {
    const el = document.createElement("tr-room-tile");
    const s = snapshot({
      job: {
        room_id: "other",
        room: "Salone",
        kind: "vacuum",
        forced: false,
        quiet: false,
        manual: false,
        phase: "running",
        created: "2026-01-12T09:40:00+01:00",
        attempts: 1,
      },
    });
    Object.assign(el, { hass: hass("en"), snapshot: s, room: room(), ctx, admin: true });
    const root = await mount(el);
    const buttons = [...root.querySelectorAll(".actions .btn")] as HTMLButtonElement[];
    expect(buttons.every((b) => b.disabled)).toBe(true);
  });
});

describe("robot card", () => {
  it("shows the job and the next room", async () => {
    const el = document.createElement("tr-robot-card");
    Object.assign(el, { hass: hass("en"), snapshot: snapshot(), ctx, admin: true });
    const root = await mount(el);
    const text = root.textContent!.replace(/\s+/g, " ");
    expect(text).toContain("Tatiana");
    expect(text).toContain("87%");
    expect(text).toContain("No job running");
    expect(text).toContain("Next: Cucina");
    expect(text).toContain("Quiet hours 22:30–08:00");
  });
});
