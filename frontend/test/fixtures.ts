// A fake snapshot and hass object for the tests.
import type { HassEntity } from "home-assistant-js-websocket";
import type { HomeAssistant, LoadedSnapshot, PassSnapshot, RoomSnapshot } from "../src/types";

export const NOW = new Date("2026-01-12T10:00:00+01:00");

export const pass = (over: Partial<PassSnapshot> = {}): PassSnapshot => ({
  id: "p",
  position: 1,
  work_mode: null,
  fan_speed: null,
  start: null,
  end: null,
  forced: true,
  gap_hours: null,
  days: null,
  status: "pending",
  done_at: null,
  manual: false,
  ...over,
});

export const room = (over: Partial<RoomSnapshot> = {}): RoomSnapshot => ({
  id: "kitchen",
  name: "Cucina",
  area_id: "cucina",
  enabled: true,
  status: "waiting_occupied",
  action_error: false,
  occupancy_sensors: ["binary_sensor.kitchen"],
  proxy_sensors: [],
  occupied: false,
  empty_since: "2026-01-12T09:56:00+01:00",
  proxy_active: false,
  empty_minutes: 10,
  passes: [
    pass({ id: "full-1", position: 1, work_mode: "mop_after_vacuum", end: "19:00:00" }),
    pass({ id: "vacuum-1", position: 2, work_mode: "vacuum", end: "21:30:00", gap_hours: 6 }),
  ],
  last_clean: null,
  last_result: null,
  custom_action: false,
  outlook: {
    pass_id: "full-1",
    position: 1,
    total: 2,
    done: 0,
    skipped: 0,
    work_mode: "mop_after_vacuum",
    earliest: "2026-01-12T10:06:00+01:00",
    reason: "empty",
    free_at: "2026-01-12T10:06:00+01:00",
    deadline: "2026-01-12T19:00:00+01:00",
    forced: true,
    not_before: "2026-01-12T10:00:00+01:00",
  },
  ...over,
});

export const snapshot = (over: Partial<LoadedSnapshot> = {}): LoadedSnapshot => ({
  loaded: true,
  entry_id: "entry",
  title: "Tatiana",
  enabled: true,
  now: NOW.toISOString(),
  awake: true,
  wake_check_today: false,
  quiet_start: "22:30:00",
  quiet_end: "08:00:00",
  min_battery: 30,
  work_mode_entity: "select.tatiana_work_mode",
  work_modes: ["vacuum", "mop_after_vacuum", "mop"],
  restore_settings: false,
  restore_pending: false,
  normal_fan_speed: "normal",
  quiet_fan_speed: "quiet",
  paused_until: null,
  robot: {
    entity_id: "vacuum.tatiana",
    name: "Tatiana",
    state: "docked",
    available: true,
    idle: true,
    battery: 87,
    fan_speed: "normal",
  },
  job: null,
  next_room: "kitchen",
  rooms: [room()],
  ...over,
});

const MODE_NAMES: Record<string, Record<string, string>> = {
  en: { vacuum: "Vacuum", mop_after_vacuum: "Vacuum then mop", mop: "Mop" },
  it: { vacuum: "Aspirazione", mop_after_vacuum: "Aspirazione poi lavaggio", mop: "Lavaggio" },
};

export const hass = (language = "it"): HomeAssistant =>
  ({
    language,
    locale: { language, time_format: "24" },
    config: { time_zone: "Europe/Rome" },
    states: {
      "select.tatiana_work_mode": { entity_id: "select.tatiana_work_mode" } as HassEntity,
    },
    formatEntityState: (stateObj: HassEntity, state?: string) =>
      (stateObj.entity_id === "select.tatiana_work_mode" && state
        ? MODE_NAMES[language]?.[state]
        : undefined) ??
      state ??
      "",
    areas: {},
    user: { is_admin: true },
    connection: {} as HomeAssistant["connection"],
    callWS: async () => undefined as never,
  }) as HomeAssistant;
