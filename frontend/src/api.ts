// WebSocket commands of the integration (custom_components/tidy_rooms/websocket_api.py).

import type {
  EntrySummary,
  FormField,
  HomeAssistant,
  JobRecord,
  RoomForm,
  SaveResult,
  Snapshot,
} from "./types";

export const listEntries = (hass: HomeAssistant) =>
  hass.callWS<EntrySummary[]>({ type: "tidy_rooms/entries" });

/** Calls `callback` with a snapshot now and after every change; resolves to the unsubscribe. */
export const subscribeSnapshot = (
  hass: HomeAssistant,
  entryId: string,
  callback: (snapshot: Snapshot) => void,
) =>
  hass.connection.subscribeMessage<Snapshot>(callback, {
    type: "tidy_rooms/subscribe",
    entry_id: entryId,
  });

export const fetchHistory = (hass: HomeAssistant, entryId: string, days: number, roomId?: string) =>
  hass.callWS<{ jobs: JobRecord[] }>({
    type: "tidy_rooms/history",
    entry_id: entryId,
    days,
    ...(roomId ? { room_id: roomId } : {}),
  });

export const fetchRoomForm = (hass: HomeAssistant, entryId: string, roomId?: string) =>
  hass.callWS<RoomForm>({
    type: "tidy_rooms/schema",
    entry_id: entryId,
    form: "room",
    ...(roomId ? { room_id: roomId } : {}),
  });

export const fetchSettingsForm = (
  hass: HomeAssistant,
  entryId: string,
  workModeEntity?: string | null,
) =>
  hass.callWS<{ sections: Record<string, FormField[]>; values: Record<string, unknown> }>({
    type: "tidy_rooms/schema",
    entry_id: entryId,
    form: "settings",
    ...(workModeEntity !== undefined ? { work_mode_entity: workModeEntity } : {}),
  });

export const saveRoom = (
  hass: HomeAssistant,
  entryId: string,
  data: Record<string, unknown>,
  roomId?: string,
) =>
  hass.callWS<SaveResult>({
    type: "tidy_rooms/room/save",
    entry_id: entryId,
    data,
    ...(roomId ? { room_id: roomId } : {}),
  });

export const deleteRoom = (hass: HomeAssistant, entryId: string, roomId: string) =>
  hass.callWS<null>({ type: "tidy_rooms/room/delete", entry_id: entryId, room_id: roomId });

export const reorderRooms = (hass: HomeAssistant, entryId: string, order: string[]) =>
  hass.callWS<null>({ type: "tidy_rooms/room/reorder", entry_id: entryId, order });

export const setRoomEnabled = (
  hass: HomeAssistant,
  entryId: string,
  roomId: string,
  enabled: boolean,
) =>
  hass.callWS<null>({
    type: "tidy_rooms/room/set_enabled",
    entry_id: entryId,
    room_id: roomId,
    enabled,
  });

export const saveSettings = (hass: HomeAssistant, entryId: string, data: Record<string, unknown>) =>
  hass.callWS<SaveResult>({ type: "tidy_rooms/settings/save", entry_id: entryId, data });

export const setEnabled = (hass: HomeAssistant, entryId: string, enabled: boolean) =>
  hass.callWS<null>({ type: "tidy_rooms/set_enabled", entry_id: entryId, enabled });

/** Clean a room now with a work mode (null: leave the robot's mode as it is). */
export const cleanNow = (
  hass: HomeAssistant,
  entryId: string,
  roomId: string,
  workMode: string | null,
) =>
  hass.callWS<null>({
    type: "tidy_rooms/clean_now",
    entry_id: entryId,
    room_id: roomId,
    work_mode: workMode,
  });

export const stopJob = (hass: HomeAssistant, entryId: string) =>
  hass.callWS<null>({ type: "tidy_rooms/stop_job", entry_id: entryId });

/** The message of an error thrown by callWS. */
export const errorMessage = (err: unknown): string => {
  if (err && typeof err === "object") {
    const e = err as { message?: string; code?: string };
    return e.message || e.code || String(err);
  }
  return String(err);
};

export const errorCode = (err: unknown): string | undefined =>
  err && typeof err === "object" ? (err as { code?: string }).code : undefined;
