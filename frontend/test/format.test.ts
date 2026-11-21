import { describe, expect, it } from "vitest";
import {
  formatClock,
  formatContext,
  formatDayTime,
  formatDuration,
  lastPass,
  outlookText,
  waitText,
} from "../src/format";
import { localizer } from "../src/localize";
import { NOW, hass, room, snapshot } from "./fixtures";

const ctx = formatContext(hass("it"), localizer("it"), NOW);

describe("times", () => {
  it("formats durations", () => {
    const t = localizer("it");
    expect(formatDuration(20_000, t)).toBe("< 1 min");
    expect(formatDuration(45 * 60_000, t)).toBe("45 min");
    expect(formatDuration(65 * 60_000, t)).toBe("1 h 05 min");
    expect(formatDuration(120 * 60_000, t)).toBe("2 h");
  });

  it("formats days in the time zone of Home Assistant", () => {
    expect(formatDayTime("2026-01-12T09:30:00+01:00", ctx)).toBe("oggi 09:30");
    expect(formatDayTime("2026-01-11T22:30:00Z", ctx)).toBe("ieri 23:30");
    expect(formatClock("19:00:00", ctx)).toBe("19:00");
  });
});

describe("room texts", () => {
  it("explains an empty room that is not free yet", () => {
    expect(waitText(room(), snapshot(), ctx)).toBe("Vuota da 4 min su 10");
  });

  it("explains an occupied room without deadline", () => {
    const r = room({ occupied: true, empty_since: null });
    r.outlook = { ...r.outlook, deadline: null };
    expect(waitText(r, snapshot(), ctx)).toBe("C'è qualcuno nella stanza");
  });

  it("explains the minimum gap", () => {
    const r = room({ status: "waiting_gap" });
    r.outlook = {
      ...r.outlook,
      kind: "vacuum",
      earliest: "2026-01-12T16:00:00+01:00",
      reason: "gap",
    };
    expect(waitText(r, snapshot(), ctx)).toBe("Prossima passata dalle 16:00 (distanza minima).");
    expect(outlookText(r, ctx)).toBe("Aspirazione dalle 16:00");
  });

  it("does not promise a start while automatic cleaning is paused", () => {
    expect(waitText(room({ status: "ready" }), snapshot(), ctx)).toBe(
      "Libera e da pulire: il robot parte a breve.",
    );
    expect(waitText(room({ status: "ready" }), snapshot({ enabled: false }), ctx)).toBe(
      "Libera e da pulire: la pulizia automatica è in pausa.",
    );
  });

  it("explains a low battery", () => {
    const s = snapshot({ robot: { ...snapshot().robot, battery: 12 } });
    expect(waitText(room({ status: "waiting_robot" }), s, ctx)).toBe(
      "Batteria al 12%, attende il 30%.",
    );
  });

  it("tells when a forced pass happens", () => {
    const r = room({ occupied: true });
    r.outlook = { ...r.outlook, earliest: r.outlook.deadline, reason: "occupied" };
    expect(outlookText(r, ctx)).toBe("Aspirazione e lavaggio entro le 19:00");
  });

  it("says when a room is done or cannot be cleaned today", () => {
    const done = room({ status: "done" });
    done.outlook = { ...done.outlook, kind: null, earliest: null, reason: null };
    expect(outlookText(done, ctx)).toBe("Obiettivi di oggi raggiunti");
    const late = room();
    late.outlook = { ...late.outlook, earliest: null, reason: "not_today" };
    expect(outlookText(late, ctx)).toBe("Aspirazione e lavaggio: non prima di domani");
  });

  it("finds the last pass", () => {
    expect(lastPass(room())).toBeNull();
    const t = "2026-01-12T09:00:00+01:00";
    expect(lastPass(room({ last_full: t, last_vacuum: t }))).toEqual({ at: t, kind: "full" });
    expect(lastPass(room({ last_full: t, last_vacuum: "2026-01-12T09:30:00+01:00" }))?.kind).toBe(
      "vacuum",
    );
  });
});
