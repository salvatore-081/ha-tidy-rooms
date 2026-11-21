// Pure formatting helpers: times, durations and the texts that explain a room.

import { workModeLabel } from "./form";
import type { Localize } from "./localize";
import type {
  HomeAssistant,
  LoadedSnapshot,
  Outlook,
  PassSnapshot,
  RoomSnapshot,
  RoomStatus,
} from "./types";

export interface FormatContext {
  language: string;
  timeZone: string;
  hour12?: boolean;
  now: Date;
  t: Localize;
  /** The name of a work mode; null: the robot's own mode, left as it is. */
  mode: (value: string | null | undefined) => string;
}

export const formatContext = (
  hass: HomeAssistant,
  t: Localize,
  now = new Date(),
  workModeEntity?: string | null,
): FormatContext => {
  const fmt = hass.locale?.time_format;
  return {
    language: hass.locale?.language || hass.language || "en",
    timeZone: hass.config.time_zone,
    hour12: fmt === "12" ? true : fmt === "24" ? false : undefined,
    now,
    t,
    mode: (value) => (value ? workModeLabel(hass, workModeEntity, value) : t("mode.robot")),
  };
};

const safeZone = (timeZone: string): string | undefined => {
  try {
    new Intl.DateTimeFormat("en", { timeZone });
    return timeZone;
  } catch {
    return undefined;
  }
};

const dayKey = (date: Date, timeZone: string): string =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: safeZone(timeZone),
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);

/** "15:20" (or "3:20 PM"), in the time zone of Home Assistant. */
export const formatTime = (iso: string | null | undefined, ctx: FormatContext): string => {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(ctx.language, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: ctx.hour12,
    timeZone: safeZone(ctx.timeZone),
  }).format(date);
};

/** A time of day from the configuration ("19:00:00"), formatted like formatTime. */
export const formatClock = (value: string | null | undefined, ctx: FormatContext): string => {
  if (!value) return "";
  const [h, m] = value.split(":").map(Number);
  if (Number.isNaN(h) || Number.isNaN(m)) return value;
  const date = new Date(Date.UTC(2000, 0, 1, h, m));
  return new Intl.DateTimeFormat(ctx.language, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: ctx.hour12,
    timeZone: "UTC",
  }).format(date);
};

/** "today 15:20", "yesterday 9:05", or "12 Jan 15:20". */
export const formatDayTime = (iso: string | null | undefined, ctx: FormatContext): string => {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const time = formatTime(iso, ctx);
  const day = dayKey(date, ctx.timeZone);
  if (day === dayKey(ctx.now, ctx.timeZone)) return ctx.t("time.today_at", { time });
  const yesterday = new Date(ctx.now.getTime() - 86_400_000);
  if (day === dayKey(yesterday, ctx.timeZone)) return ctx.t("time.yesterday_at", { time });
  const date_ = new Intl.DateTimeFormat(ctx.language, {
    day: "numeric",
    month: "short",
    timeZone: safeZone(ctx.timeZone),
  }).format(date);
  return ctx.t("time.date_at", { date: date_, time });
};

/** "45 min", "1 h 05 min", "< 1 min". */
export const formatDuration = (ms: number, t: Localize): string => {
  const minutes = Math.round(ms / 60_000);
  if (minutes < 1) return t("time.less_than_minute");
  if (minutes < 60) return t("time.minutes", { n: minutes });
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m === 0
    ? t("time.hours", { n: h })
    : t("time.hours_minutes", { h, m: String(m).padStart(2, "0") });
};

export const minutesSince = (iso: string | null | undefined, now: Date): number | null => {
  if (!iso) return null;
  const ms = now.getTime() - new Date(iso).getTime();
  return Number.isNaN(ms) ? null : Math.max(0, Math.floor(ms / 60_000));
};

// ------------------------------------------------------------- rooms

export type Tone = "success" | "active" | "ready" | "waiting" | "warning" | "error" | "off";

export const statusIcon = (room: RoomSnapshot): string => {
  if (room.action_error) return "mdi:alert-circle-outline";
  const icons: Record<RoomStatus, string> = {
    disabled: "mdi:pause-circle-outline",
    done: "mdi:check-circle-outline",
    waiting_window: "mdi:clock-start",
    waiting_gap: "mdi:timer-sand",
    waiting_occupied: "mdi:account-clock-outline",
    waiting_quiet_hours: "mdi:weather-night",
    waiting_awake: "mdi:sleep",
    waiting_robot: "mdi:robot-vacuum-alert",
    ready: "mdi:play-circle-outline",
    cleaning: "mdi:robot-vacuum",
  };
  return room.status ? icons[room.status] : "mdi:help-circle-outline";
};

export const statusTone = (room: RoomSnapshot): Tone => {
  if (room.action_error) return "error";
  switch (room.status) {
    case "done":
      return "success";
    case "cleaning":
      return "active";
    case "ready":
      return "ready";
    case "waiting_robot":
      return "warning";
    case "disabled":
    case null:
      return "off";
    default:
      return "waiting";
  }
};

export const statusLabel = (room: RoomSnapshot, t: Localize): string =>
  room.action_error ? t("status.action_error") : t(`status.${room.status ?? "unknown"}`);

/** Why the robot is not taking a job, if it is not. */
export const robotBlocker = (snap: LoadedSnapshot, t: Localize, ctx: FormatContext): string => {
  const robot = snap.robot;
  if (snap.paused_until)
    return t("wait.robot_paused", { time: formatTime(snap.paused_until, ctx) });
  if (!robot.available) return t("wait.robot_unavailable");
  if (snap.job) return t("wait.robot_busy_job", { room: snap.job.room });
  if (robot.battery !== null && robot.battery < snap.min_battery)
    return t("wait.robot_battery", { battery: robot.battery, min: snap.min_battery });
  if (!robot.idle) return t("wait.robot_busy");
  return t("wait.robot_busy");
};

/** One line that explains what the room is waiting for, with numbers. */
export const waitText = (room: RoomSnapshot, snap: LoadedSnapshot, ctx: FormatContext): string => {
  const { t } = ctx;
  const ol = room.outlook;
  if (room.action_error) return t("wait.action_error");
  switch (room.status) {
    case "cleaning":
      return snap.job
        ? t("wait.cleaning", { mode: ctx.mode(snap.job.work_mode) }) +
            (snap.job.quiet ? ` · ${t("wait.quiet")}` : "")
        : t("status.cleaning");
    case "done":
      if (ol.total === 0) return t("wait.nothing_today");
      return ol.skipped ? t("wait.done_skipped", { n: ol.skipped }) : t("wait.done");
    case "disabled":
      return t("wait.disabled");
    case "waiting_window":
      return t("wait.window", { time: formatTime(ol.earliest, ctx) });
    case "waiting_gap":
      return t("wait.gap", { time: formatTime(ol.earliest, ctx) });
    case "waiting_quiet_hours":
      return t("wait.quiet_hours", { time: formatClock(snap.quiet_end, ctx) });
    case "waiting_awake":
      return t("wait.awake");
    case "waiting_robot":
      return robotBlocker(snap, t, ctx);
    case "ready":
      return t(snap.enabled ? "wait.ready" : "wait.ready_paused");
    case "waiting_occupied": {
      let text: string;
      if (room.occupancy_sensors.length) {
        if (room.occupied === null) text = t("wait.sensors_unavailable");
        else if (room.occupied) text = t("wait.occupied");
        else
          text = t("wait.empty_for", {
            n: minutesSince(room.empty_since, ctx.now) ?? 0,
            m: room.empty_minutes,
          });
      } else {
        text = t("wait.proxy");
      }
      return text;
    }
    default:
      return "";
  }
};

/** "Vacuum (2/3)": the work mode of a pass and where it is in today's program. */
export const passLabel = (ol: Outlook, ctx: FormatContext): string =>
  ol.total > 1
    ? ctx.t("pass.label", { mode: ctx.mode(ol.work_mode), n: ol.position, total: ol.total })
    : ctx.mode(ol.work_mode);

/** When the next pass can start: "Vacuum (2/3) from 15:20", "Vacuum now"... */
export const outlookText = (room: RoomSnapshot, ctx: FormatContext): string => {
  const { t } = ctx;
  const ol = room.outlook;
  if (!room.enabled || room.action_error) return "";
  if (ol.pass_id === null) return t(ol.total === 0 ? "outlook.nothing_today" : "outlook.all_done");
  const what = passLabel(ol, ctx);
  if (ol.reason === "not_today") return t("outlook.not_today", { what });
  if (ol.earliest === null) return t("outlook.when_free", { what });
  const forced = ol.forced && ol.deadline !== null && ol.earliest >= ol.deadline;
  const at = new Date(ol.earliest).getTime();
  if (at <= ctx.now.getTime() + 30_000) {
    if (ol.reason === "awake") return t("outlook.after_wake_up", { what });
    return t(forced ? "outlook.now_forced" : "outlook.now", { what });
  }
  return t(forced ? "outlook.forced_at" : "outlook.from", {
    what,
    time: formatTime(ol.earliest, ctx),
  });
};

/** The window of a pass: "09:00–12:00", "until 19:00", "from 17:00", "any time". */
export const passWindow = (p: PassSnapshot, ctx: FormatContext): string => {
  const { t } = ctx;
  const start = formatClock(p.start, ctx);
  const end = formatClock(p.end, ctx);
  if (start && end) return t("pass.window", { start, end });
  if (end) return t("pass.until", { time: end });
  if (start) return t("pass.from", { time: start });
  return t("pass.any_time");
};

/** Minutes since midnight of a time of day ("19:00:00"), or null. */
export const clockMinutes = (value: string | null | undefined): number | null => {
  if (!value) return null;
  const [h, m] = value.split(":").map(Number);
  return Number.isNaN(h) || Number.isNaN(m) ? null : h * 60 + m;
};

/** Minutes since midnight of a moment, in the time zone of Home Assistant. */
export const dayMinutes = (
  iso: string | Date | null | undefined,
  ctx: FormatContext,
): number | null => {
  if (!iso) return null;
  const date = typeof iso === "string" ? new Date(iso) : iso;
  if (Number.isNaN(date.getTime())) return null;
  const parts = new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: safeZone(ctx.timeZone),
  }).formatToParts(date);
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value ?? 0);
  return get("hour") * 60 + get("minute");
};

/** The pass a cleaning with `mode` counts as (as the integration decides), if any. */
export const manualTarget = (
  room: RoomSnapshot,
  mode: string | null,
  anyMode = false,
): PassSnapshot | undefined =>
  room.passes.find(
    (p) => (p.status === "pending" || p.status === "skipped") && (anyMode || p.work_mode === mode),
  );

/** The work mode offered first by "clean now": the next pass's, else the last pass's. */
export const defaultCleanMode = (room: RoomSnapshot): string | null =>
  room.outlook.pass_id !== null
    ? room.outlook.work_mode
    : (room.passes[room.passes.length - 1]?.work_mode ?? null);

/** The work mode of a logged job; jobs of 0.3.0 have a kind instead. */
export const jobMode = (
  job: { work_mode?: string | null; kind?: string | null },
  ctx: FormatContext,
): string =>
  job.work_mode ? ctx.mode(job.work_mode) : job.kind ? ctx.t(`kind.${job.kind}`) : ctx.mode(null);
