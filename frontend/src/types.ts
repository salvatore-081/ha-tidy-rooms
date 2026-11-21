// Shapes of the data sent by the integration (websocket_api.py, engine.snapshot).

import type { Connection, HassEntity } from "home-assistant-js-websocket";

/** Kind of pass of Tidy Rooms 0.3.0: only in jobs logged by that version. */
export type LegacyKind = "full" | "vacuum";

export type RoomStatus =
  | "disabled"
  | "done"
  | "waiting_window"
  | "waiting_gap"
  | "waiting_occupied"
  | "waiting_quiet_hours"
  | "waiting_awake"
  | "waiting_robot"
  | "ready"
  | "cleaning";

export type WaitReason =
  "window" | "gap" | "quiet_hours" | "awake" | "empty" | "occupied" | "not_today";

export type PassStatus = "not_today" | "done" | "active" | "skipped" | "pending";

export type Weekday = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";

export type JobPhase = "starting" | "running" | "finishing";

export type JobResult = "done" | "interrupted" | "failed" | "stopped";

/** When the next pass of a room can start (an estimate). */
export interface Outlook {
  /** The next pass still due today; null when nothing is left. */
  pass_id: string | null;
  /** 1-based among today's passes (0 without a next pass). */
  position: number;
  total: number;
  done: number;
  skipped: number;
  work_mode: string | null;
  earliest: string | null;
  reason: WaitReason | null;
  free_at: string | null;
  deadline: string | null;
  forced: boolean;
  /** When the window, the gap and quiet hours allow the pass, presence aside. */
  not_before: string | null;
}

/** A pass of a room's program, with where it stands today. */
export interface PassSnapshot {
  id: string;
  /** 1-based among today's passes; null when not planned today. */
  position: number | null;
  work_mode: string | null;
  fan_speed: string | null;
  start: string | null;
  end: string | null;
  forced: boolean;
  gap_hours: number | null;
  days: Weekday[] | null;
  status: PassStatus;
  done_at: string | null;
  manual: boolean;
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
  passes: PassSnapshot[];
  last_clean: string | null;
  last_result: JobResult | null;
  custom_action: boolean;
  outlook: Outlook;
}

export interface JobSnapshot {
  room_id: string;
  room: string;
  /** null: a manual cleaning that does not count as a pass. */
  pass_id: string | null;
  /** null: the robot's work mode was left as it was. */
  work_mode: string | null;
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
  /** supported_features of the vacuum entity. */
  features: number;
  /** Button entities of the robot's own device (empty the dustbin, wash the mop…). */
  buttons: string[];
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
  work_mode_entity: string | null;
  /** Options of the work mode entity (empty if none or unknown). */
  work_modes: string[];
  restore_settings: boolean;
  restore_pending: boolean;
  normal_fan_speed: string | null;
  quiet_fan_speed: string | null;
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
  work_mode?: string | null;
  /** null: a manual cleaning that did not count as a pass. */
  pass_id?: string | null;
  /** Jobs logged by 0.3.0. */
  kind?: LegacyKind | null;
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

/** The room form: ha-form schemas and the room's program. */
export interface RoomForm {
  schema: FormField[];
  values: Record<string, unknown>;
  pass_schema: FormField[];
  pass_defaults: Record<string, unknown>;
  passes: PassData[];
  max_passes: number;
}

/** A pass as saved (and edited): no id for a new one. */
export type PassData = Record<string, unknown> & { id?: string };

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
  formatEntityAttributeValue?(stateObj: HassEntity, attribute: string, value?: unknown): string;
}
