// Shapes of the data sent by the integration (websocket_api.py, engine.snapshot).

import type { Connection, HassEntity } from "home-assistant-js-websocket";

export type CleanKind = "full" | "vacuum";

export type RoomStatus =
  | "disabled"
  | "done"
  | "waiting_gap"
  | "waiting_occupied"
  | "waiting_quiet_hours"
  | "waiting_awake"
  | "waiting_robot"
  | "ready"
  | "cleaning";

export type WaitReason = "gap" | "quiet_hours" | "awake" | "empty" | "occupied" | "not_today";

export type JobPhase = "starting" | "running" | "finishing";

export type JobResult = "done" | "interrupted" | "failed" | "stopped";

export interface Outlook {
  kind: CleanKind | null;
  earliest: string | null;
  reason: WaitReason | null;
  free_at: string | null;
  deadline: string | null;
  full_left: number;
  vacuum_left: number;
}

export interface RoomSnapshot {
  id: string;
  name: string;
  area_id: string;
  enabled: boolean;
  status: RoomStatus | null;
  action_error: boolean;
  occupancy_sensors: string[];
  proxy_sensors: string[];
  occupied: boolean | null;
  empty_since: string | null;
  proxy_active: boolean;
  empty_minutes: number;
  full_today: number;
  full_per_day: number;
  vacuum_today: number;
  vacuum_per_day: number;
  min_gap_hours: number;
  full_deadline: string | null;
  vacuum_deadline: string | null;
  last_full: string | null;
  last_vacuum: string | null;
  last_result: JobResult | null;
  custom_action: boolean;
  outlook: Outlook;
}

export interface JobSnapshot {
  room_id: string;
  room: string;
  kind: CleanKind;
  forced: boolean;
  quiet: boolean;
  manual: boolean;
  phase: JobPhase;
  created: string;
  attempts: number;
}

export interface RobotSnapshot {
  entity_id: string;
  name: string;
  state: string | null;
  available: boolean;
  idle: boolean;
  battery: number | null;
  fan_speed: string | null;
}

export interface LoadedSnapshot {
  loaded: true;
  entry_id: string;
  title: string;
  enabled: boolean;
  now: string;
  awake: boolean;
  wake_check_today: boolean;
  quiet_start: string | null;
  quiet_end: string | null;
  min_battery: number;
  paused_until: string | null;
  robot: RobotSnapshot;
  job: JobSnapshot | null;
  next_room: string | null;
  rooms: RoomSnapshot[];
}

export type Snapshot = LoadedSnapshot | { loaded: false; entry_id: string };

export interface EntrySummary {
  entry_id: string;
  title: string;
  vacuum: string;
  loaded: boolean;
}

export interface JobRecord {
  room_id: string;
  room: string;
  kind: CleanKind;
  forced: boolean;
  quiet: boolean;
  manual: boolean;
  attempts: number;
  started: string;
  ended: string;
  result: JobResult;
}

/** A field of ha-form, as serialized by the integration. */
export interface FormField {
  name: string;
  required?: boolean;
  optional?: boolean;
  selector?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface SaveResult {
  errors?: Record<string, string>;
  room_id?: string;
}

/** The parts of the frontend's `hass` object that Tidy Rooms uses. */
export interface HomeAssistant {
  connection: Connection;
  language: string;
  locale?: { language: string; time_format?: string };
  config: { time_zone: string };
  states: Record<string, HassEntity>;
  areas?: Record<string, { area_id: string; name: string; icon?: string | null }>;
  user?: { is_admin: boolean };
  callWS<T>(msg: Record<string, unknown>): Promise<T>;
  formatEntityState?(stateObj: HassEntity, state?: string): string;
}
