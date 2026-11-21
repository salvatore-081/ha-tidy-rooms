import { describe, expect, it } from "vitest";
import "../src/components/tr-room-tile";
import "../src/components/tr-robot-card";
import "../src/components/tr-timeline";
import "../src/components/tr-program-editor";
import { choiceDialog } from "../src/components/tr-confirm";
import { passErrors, passSummary, windowInDnd } from "../src/components/tr-program-editor";
import { quietRanges } from "../src/components/tr-timeline";
import { formatContext } from "../src/format";
import { localizer } from "../src/localize";
import type { HassEntity } from "home-assistant-js-websocket";
import type { HomeAssistant } from "../src/types";
import { NOW, hass, pass, room, snapshot } from "./fixtures";

const ctx = formatContext(hass("en"), localizer("en"), NOW, "select.tatiana_work_mode");

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
    expect(text).toContain("Vacuum then mop (1/2) from 10:06");
    expect(text).toContain("Not cleaned yet");
    expect(root.querySelectorAll(".actions .btn")).toHaveLength(1);
    expect(root.querySelector("tr-passes")).not.toBeNull();
    expect(root.querySelector("tr-timeline")).not.toBeNull();
  });

  it("emits clean-now for the room", async () => {
    const el = document.createElement("tr-room-tile");
    Object.assign(el, { hass: hass("en"), snapshot: snapshot(), room: room(), ctx, admin: true });
    const root = await mount(el);
    let detail: unknown;
    el.addEventListener("clean-now", (ev) => (detail = (ev as CustomEvent).detail));
    (root.querySelector(".actions .btn") as HTMLButtonElement).click();
    expect(detail).toEqual({ room: "kitchen" });
  });

  it("disables the buttons while the robot is busy", async () => {
    const el = document.createElement("tr-room-tile");
    const s = snapshot({
      job: {
        room_id: "other",
        room: "Salone",
        pass_id: "vacuum-1",
        work_mode: "vacuum",
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
    expect(text).toContain("Do not disturb 22:30–08:00");
  });
});

describe("robot commands", () => {
  it("offers back to the dock, locate and the buttons of the robot's device", async () => {
    const h = hass("en");
    const calls: unknown[] = [];
    h.callWS = (async (msg: unknown) => {
      calls.push(msg);
      return null;
    }) as HomeAssistant["callWS"];
    h.states["button.tatiana_empty"] = {
      entity_id: "button.tatiana_empty",
      state: "unknown",
      attributes: { friendly_name: "Tatiana Empty the dustbin" },
    } as unknown as HassEntity;
    const s = snapshot({
      robot: { ...snapshot().robot, buttons: ["button.tatiana_empty", "button.missing"] },
    });
    const el = document.createElement("tr-robot-card");
    Object.assign(el, { hass: h, snapshot: s, ctx, admin: true });
    const root = await mount(el);
    const buttons = [...root.querySelectorAll(".actions .btn")] as HTMLButtonElement[];
    expect(buttons.map((b) => b.textContent!.trim())).toEqual([
      "Back to the dock",
      "Locate",
      "Empty the dustbin",
    ]);
    buttons[2].click();
    expect(calls).toEqual([
      {
        type: "call_service",
        domain: "button",
        service: "press",
        target: { entity_id: "button.tatiana_empty" },
      },
    ]);
  });

  it("stops a job of Tidy Rooms instead of sending the robot home behind its back", async () => {
    const s = snapshot({
      job: {
        room_id: "kitchen",
        room: "Cucina",
        pass_id: "full-1",
        work_mode: "mop_after_vacuum",
        forced: false,
        quiet: false,
        manual: false,
        phase: "running",
        created: "2026-01-12T09:40:00+01:00",
        attempts: 1,
      },
    });
    const el = document.createElement("tr-robot-card");
    Object.assign(el, { hass: hass("en"), snapshot: s, ctx, admin: true });
    const root = await mount(el);
    let stopped = false;
    el.addEventListener("stop-job", () => (stopped = true));
    (root.querySelector(".actions .btn") as HTMLButtonElement).click();
    expect(stopped).toBe(true);
  });

  it("has no commands for users who are not admins", async () => {
    const el = document.createElement("tr-robot-card");
    Object.assign(el, { hass: hass("en"), snapshot: snapshot(), ctx, admin: false });
    const root = await mount(el);
    expect(root.querySelector(".actions")).toBeNull();
  });
});

describe("passes and timeline", () => {
  const passes = [
    pass({
      id: "a",
      position: 1,
      work_mode: "mop_after_vacuum",
      end: "12:00:00",
      status: "done",
      done_at: "2026-01-12T09:30:00+01:00",
    }),
    pass({
      id: "b",
      position: 2,
      work_mode: "vacuum",
      start: "17:00:00",
      status: "pending",
      forced: false,
    }),
    pass({ id: "c", position: null, work_mode: "mop", status: "not_today" }),
    pass({ id: "d", position: 3, work_mode: "vacuum", end: "08:30:00", status: "skipped" }),
  ];

  it("draws a dot per pass of today", async () => {
    const el = document.createElement("tr-passes");
    Object.assign(el, { passes, ctx });
    const root = await mount(el);
    const dots = [...root.querySelectorAll(".dot")];
    expect(dots.map((d) => d.className.replace("dot ", ""))).toEqual([
      "done",
      "pending",
      "skipped",
    ]);
    expect(dots[0].getAttribute("title")).toBe("Vacuum then mop, until 12:00: done at 09:30");
    expect(root.textContent).toContain("1/3");
  });

  it("draws the windows, the cleanings done, quiet hours and now", async () => {
    const el = document.createElement("tr-timeline");
    Object.assign(el, { passes, ctx, quietStart: "22:30:00", quietEnd: "08:00:00", labels: true });
    const root = await mount(el);
    expect(root.querySelectorAll(".window")).toHaveLength(3);
    expect(root.querySelectorAll(".window.loose")).toHaveLength(1);
    expect(root.querySelectorAll(".mark")).toHaveLength(1);
    expect(root.querySelectorAll(".quiet")).toHaveLength(2);
    const now = root.querySelector(".now") as HTMLElement;
    expect(now.style.left).toBe(`${(600 / 1440) * 100}%`);
    expect(quietRanges("09:00:00", "17:00:00")).toEqual([[540, 1020]]);
    expect(quietRanges(null, "08:00:00")).toEqual([]);
  });
});

describe("program editor", () => {
  it("splits the save errors by pass and sums up a pass", () => {
    expect(
      passErrors({ "passes.1.end": "end_before_start", "passes.0.start": "x", area: "y" }, 1),
    ).toEqual({
      end: "end_before_start",
    });
    expect(passSummary({ work_mode: "vacuum", start: "17:00:00", days: ["sat", "sun"] }, ctx)).toBe(
      "Vacuum · from 17:00 · Sat, Sun",
    );
  });

  it("warns about windows within do not disturb", () => {
    const q = ["22:30:00", "07:00:00"] as const;
    expect(windowInDnd({ start: "23:00:00", end: "23:59:00" }, ...q)).toBe(true);
    expect(windowInDnd({ end: "06:00:00" }, ...q)).toBe(true);
    expect(windowInDnd({ end: "08:00:00" }, ...q)).toBe(false);
    expect(windowInDnd({}, ...q)).toBe(false);
    expect(windowInDnd({ end: "06:00:00" }, null, null)).toBe(false);
  });

  it("adds, moves and removes passes", async () => {
    const el = document.createElement("tr-program-editor");
    Object.assign(el, {
      hass: hass("en"),
      ctx,
      schema: [],
      passes: [
        { id: "a", work_mode: "mop_after_vacuum" },
        { id: "b", work_mode: "vacuum" },
      ],
      defaults: { forced: true },
      max: 3,
    });
    const root = await mount(el);
    const events: unknown[] = [];
    el.addEventListener("passes-changed", (ev) => events.push((ev as CustomEvent).detail.passes));
    const buttons = () => [...root.querySelectorAll("button")] as HTMLButtonElement[];
    expect(root.querySelectorAll(".pass")).toHaveLength(2);
    buttons()[buttons().length - 1].click(); // add
    expect(events.at(-1)).toEqual([
      { id: "a", work_mode: "mop_after_vacuum" },
      { id: "b", work_mode: "vacuum" },
      { forced: true, work_mode: "vacuum" },
    ]);
    (root.querySelector('[aria-label="Move pass 2 up"]') as HTMLButtonElement).click();
    expect(events.at(-1)).toEqual([
      { id: "b", work_mode: "vacuum" },
      { id: "a", work_mode: "mop_after_vacuum" },
    ]);
    el.passes = [{}, {}, {}];
    await el.updateComplete;
    expect(buttons()[buttons().length - 1].disabled).toBe(true); // at the maximum
  });
});

describe("clean now", () => {
  it("offers the work modes with the next pass's first", async () => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const picked = choiceDialog(host, {
      title: "Clean?",
      text: "Mode:",
      confirm: "Start",
      cancel: "Cancel",
      choices: [
        { value: "vacuum", label: "Vacuum" },
        { value: "mop", label: "Mop", hint: "Does not count" },
      ],
      selected: "mop",
    });
    const dialog = host.querySelector("tr-confirm")!;
    await dialog.updateComplete;
    const radios = [...dialog.shadowRoot!.querySelectorAll("input")] as HTMLInputElement[];
    expect(radios.map((r) => r.checked)).toEqual([false, true]);
    radios[0].click();
    await dialog.updateComplete;
    (dialog.shadowRoot!.querySelector(".confirm") as HTMLButtonElement).click();
    expect(await picked).toBe("vacuum");
  });
});
