// A fake snapshot and hass object for the tests.
import type { HomeAssistant, LoadedSnapshot, RoomSnapshot } from "../src/types";

export const NOW = new Date("2026-01-12T10:00:00+01:00");

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
  full_today: 0,
  full_per_day: 1,
  vacuum_today: 0,
  vacuum_per_day: 2,
  min_gap_hours: 6,
  full_deadline: "19:00:00",
  vacuum_deadline: "21:30:00",
  last_full: null,
  last_vacuum: null,
  last_result: null,
  custom_action: false,
  outlook: {
    kind: "full",
    earliest: "2026-01-12T10:06:00+01:00",
    reason: "empty",
    free_at: "2026-01-12T10:06:00+01:00",
    deadline: "2026-01-12T19:00:00+01:00",
    full_left: 1,
    vacuum_left: 2,
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

export const hass = (language = "it"): HomeAssistant =>
  ({
    language,
    locale: { language, time_format: "24" },
    config: { time_zone: "Europe/Rome" },
    states: {},
    areas: {},
    user: { is_admin: true },
    connection: {} as HomeAssistant["connection"],
    callWS: async () => undefined as never,
  }) as HomeAssistant;
