import { describe, expect, it } from "vitest";
import {
  dayMinutes,
  defaultCleanMode,
  formatClock,
  formatContext,
  formatDayTime,
  formatDuration,
  jobMode,
  manualTarget,
  outlookText,
  passWindow,
  waitText,
} from "../src/format";
import { localizer } from "../src/localize";
import { NOW, hass, pass, room, snapshot } from "./fixtures";

const ctx = formatContext(hass("it"), localizer("it"), NOW, "select.tatiana_work_mode");

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

  it("explains the minimum gap and the window", () => {
    const r = room({ status: "waiting_gap" });
    r.outlook = {
      ...r.outlook,
      pass_id: "vacuum-1",
      position: 2,
      done: 1,
      work_mode: "vacuum",
      earliest: "2026-01-12T16:00:00+01:00",
      reason: "gap",
    };
    expect(waitText(r, snapshot(), ctx)).toBe("Prossima passata dalle 16:00 (distanza minima).");
    expect(outlookText(r, ctx)).toBe("Aspirazione (2/2) dalle 16:00");
    r.status = "waiting_window";
    expect(waitText(r, snapshot(), ctx)).toBe("Prossima passata dalle 16:00.");
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
    expect(outlookText(r, ctx)).toBe("Aspirazione poi lavaggio (1/2) alle 19:00 al più tardi");
    r.outlook = { ...r.outlook, forced: false };
    expect(outlookText(r, ctx)).toBe("Aspirazione poi lavaggio (1/2) dalle 19:00");
  });

  it("says when a room is done, has nothing today or cannot be cleaned today", () => {
    const done = room({ status: "done" });
    done.outlook = {
      ...done.outlook,
      pass_id: null,
      earliest: null,
      reason: null,
      done: 1,
      skipped: 1,
    };
    expect(outlookText(done, ctx)).toBe("Programma di oggi completato");
    expect(waitText(done, snapshot(), ctx)).toBe("Finito per oggi; saltate: 1.");
    done.outlook = { ...done.outlook, total: 0, done: 0, skipped: 0 };
    expect(outlookText(done, ctx)).toBe("Niente in programma oggi");
    expect(waitText(done, snapshot(), ctx)).toBe("Nessuna passata prevista oggi.");
    const late = room();
    late.outlook = { ...late.outlook, total: 1, earliest: null, reason: "not_today" };
    expect(outlookText(late, ctx)).toBe("Aspirazione poi lavaggio: non prima di domani");
  });

  it("describes windows and the robot's own mode", () => {
    expect(passWindow(pass({ start: "09:00:00", end: "12:00:00" }), ctx)).toBe("09:00–12:00");
    expect(passWindow(pass({ end: "19:00:00" }), ctx)).toBe("entro le 19:00");
    expect(passWindow(pass({ start: "17:00:00" }), ctx)).toBe("dalle 17:00");
    expect(passWindow(pass(), ctx)).toBe("a qualsiasi ora");
    expect(ctx.mode(null)).toBe("Modalità attuale del robot");
    expect(jobMode({ work_mode: "vacuum" }, ctx)).toBe("Aspirazione");
    expect(jobMode({ kind: "full" }, ctx)).toBe("Aspirazione e lavaggio");
  });

  it("knows which pass a manual cleaning counts as", () => {
    const r = room();
    expect(manualTarget(r, "vacuum")?.id).toBe("vacuum-1");
    expect(manualTarget(r, "mop")).toBeUndefined();
    expect(manualTarget(r, null, true)?.id).toBe("full-1");
    expect(defaultCleanMode(r)).toBe("mop_after_vacuum");
    r.outlook = { ...r.outlook, pass_id: null };
    expect(defaultCleanMode(r)).toBe("vacuum");
  });

  it("finds the minutes of the day in the time zone of Home Assistant", () => {
    expect(dayMinutes("2026-01-12T09:30:00Z", ctx)).toBe(10 * 60 + 30);
  });
});
