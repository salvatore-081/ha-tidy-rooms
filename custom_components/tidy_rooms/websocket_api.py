"""WebSocket API of the panel and of the card."""

from __future__ import annotations

import time
from dataclasses import asdict
from functools import wraps
from types import MappingProxyType
from typing import Any

import probatio
import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry, ConfigEntryState, ConfigSubentry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .const import (
    CONF_AREA,
    CONF_ROOM_ORDER,
    CONF_VACUUM,
    CONF_WORK_MODE_ENTITY,
    DOMAIN,
    SUBENTRY_ROOM,
)
from .engine import TidyRoomsEngine, update_signal
from .history import HISTORY_DAYS
from .schema import (
    ROOM_DEFAULTS,
    room_schema,
    room_title,
    settings_keys,
    settings_sections,
    validate_room,
)

# At most one snapshot per subscription in this many seconds.
THROTTLE = 0.5

ERR_NOT_FOUND = "not_found"
ERR_NOT_LOADED = "not_loaded"
ERR_ROBOT_BUSY = "robot_busy"


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register the commands."""
    for command in (
        ws_entries,
        ws_subscribe,
        ws_history,
        ws_schema,
        ws_room_save,
        ws_room_delete,
        ws_room_reorder,
        ws_room_set_enabled,
        ws_settings_save,
        ws_set_enabled,
        ws_clean_now,
        ws_stop_job,
    ):
        websocket_api.async_register_command(hass, command)


class _Error(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _entry(hass: HomeAssistant, entry_id: str) -> ConfigEntry:
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise _Error(ERR_NOT_FOUND, "Unknown Tidy Rooms entry")
    return entry


def _engine(hass: HomeAssistant, entry_id: str) -> TidyRoomsEngine:
    entry = _entry(hass, entry_id)
    if entry.state is not ConfigEntryState.LOADED:
        raise _Error(ERR_NOT_LOADED, "Tidy Rooms entry is not loaded")
    return entry.runtime_data


def _room(entry: ConfigEntry, room_id: str) -> ConfigSubentry:
    sub = entry.subentries.get(room_id)
    if sub is None or sub.subentry_type != SUBENTRY_ROOM:
        raise _Error(ERR_NOT_FOUND, "Unknown room")
    return sub


def _handle(func):
    """Turn _Error and HomeAssistantError into WebSocket errors."""

    @wraps(func)
    async def wrapper(hass, connection, msg):
        try:
            await func(hass, connection, msg)
        except _Error as err:
            connection.send_error(msg["id"], err.code, str(err))
        except HomeAssistantError as err:
            code = getattr(err, "translation_key", None) or "error"
            connection.send_error(msg["id"], code, str(err))

    return wrapper


def _serialize(schema: vol.Schema) -> list[dict[str, Any]]:
    # Same serialization as the config flows (HA 2026.10 and later).
    return probatio.to_field_list(schema, custom_serializer=cv.custom_serializer)


def _field_errors(err: vol.Invalid) -> dict[str, str]:
    errors: dict[str, str] = {}
    for e in err.errors if isinstance(err, vol.MultipleInvalid) else [err]:
        field = str(e.path[0]) if e.path else "base"
        errors[field] = "invalid"
    return errors


def _snapshot(hass: HomeAssistant, entry_id: str) -> dict[str, Any]:
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.state is not ConfigEntryState.LOADED:
        return {"entry_id": entry_id, "loaded": False}
    return {"loaded": True, **entry.runtime_data.snapshot()}


# ------------------------------------------------------------------- read


@websocket_api.websocket_command({vol.Required("type"): "tidy_rooms/entries"})
@callback
def ws_entries(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """The robots managed by Tidy Rooms."""
    connection.send_result(
        msg["id"],
        [
            {
                "entry_id": e.entry_id,
                "title": e.title,
                "vacuum": e.data.get(CONF_VACUUM),
                "loaded": e.state is ConfigEntryState.LOADED,
            }
            for e in hass.config_entries.async_entries(DOMAIN)
        ],
    )


@websocket_api.websocket_command(
    {vol.Required("type"): "tidy_rooms/subscribe", vol.Required("entry_id"): str}
)
@websocket_api.async_response
@_handle
async def ws_subscribe(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Send a snapshot now and after every change (throttled)."""
    entry_id = _entry(hass, msg["entry_id"]).entry_id
    last_sent = 0.0
    timer: CALLBACK_TYPE | None = None

    @callback
    def send(_now: Any = None) -> None:
        nonlocal last_sent, timer
        timer = None
        last_sent = time.monotonic()
        connection.send_message(
            websocket_api.event_message(msg["id"], _snapshot(hass, entry_id))
        )

    @callback
    def on_update() -> None:
        nonlocal timer
        if timer is not None:
            return
        wait = THROTTLE - (time.monotonic() - last_sent)
        if wait <= 0:
            send()
        else:
            timer = async_call_later(hass, wait, send)

    unsub = async_dispatcher_connect(hass, update_signal(entry_id), on_update)

    @callback
    def cancel() -> None:
        unsub()
        if timer is not None:
            timer()

    connection.subscriptions[msg["id"]] = cancel
    connection.send_result(msg["id"])
    send()


@websocket_api.websocket_command(
    {
        vol.Required("type"): "tidy_rooms/history",
        vol.Required("entry_id"): str,
        vol.Optional("days", default=7): vol.All(int, vol.Range(min=1, max=HISTORY_DAYS)),
        vol.Optional("room_id"): str,
    }
)
@websocket_api.async_response
@_handle
async def ws_history(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Jobs of the last days, newest first."""
    engine = _engine(hass, msg["entry_id"])
    records = engine.history.query(dt_util.now(), msg["days"], msg.get("room_id"))
    connection.send_result(msg["id"], {"jobs": [asdict(r) for r in records]})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "tidy_rooms/schema",
        vol.Required("entry_id"): str,
        vol.Required("form"): vol.In(["room", "settings"]),
        vol.Optional("room_id"): str,
        vol.Optional("work_mode_entity"): vol.Any(str, None),
    }
)
@websocket_api.async_response
@_handle
async def ws_schema(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """A form for ha-form, with its current values."""
    entry = _entry(hass, msg["entry_id"])
    if msg["form"] == "room":
        values = (
            dict(_room(entry, msg["room_id"]).data)
            if "room_id" in msg
            else dict(ROOM_DEFAULTS)
        )
        connection.send_result(
            msg["id"],
            {"schema": _serialize(room_schema(hass, entry)), "values": values},
        )
        return
    work_mode = msg.get("work_mode_entity", entry.options.get(CONF_WORK_MODE_ENTITY))
    sections = settings_sections(hass, entry, work_mode)
    keys = settings_keys()
    connection.send_result(
        msg["id"],
        {
            "sections": {name: _serialize(s) for name, s in sections.items()},
            "values": {k: v for k, v in entry.options.items() if k in keys},
        },
    )


# ------------------------------------------------------------------ write


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "tidy_rooms/room/save",
        vol.Required("entry_id"): str,
        vol.Optional("room_id"): str,
        vol.Required("data"): dict,
    }
)
@websocket_api.async_response
@_handle
async def ws_room_save(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Add or edit a room; field errors come back in the result."""
    entry = _entry(hass, msg["entry_id"])
    current = _room(entry, msg["room_id"]) if "room_id" in msg else None
    try:
        data = room_schema(hass, entry)(msg["data"])
    except vol.Invalid as err:
        connection.send_result(msg["id"], {"errors": _field_errors(err)})
        return
    errors = validate_room(entry, data, current.subentry_id if current else None)
    if errors:
        connection.send_result(msg["id"], {"errors": errors})
        return
    title = room_title(hass, data)
    if current is None:
        sub = ConfigSubentry(
            data=MappingProxyType(data),
            subentry_type=SUBENTRY_ROOM,
            title=title,
            unique_id=data[CONF_AREA],
        )
        hass.config_entries.async_add_subentry(entry, sub)
        room_id = sub.subentry_id
    else:
        hass.config_entries.async_update_subentry(
            entry, current, data=data, title=title, unique_id=data[CONF_AREA]
        )
        room_id = current.subentry_id
    connection.send_result(msg["id"], {"room_id": room_id})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "tidy_rooms/room/delete",
        vol.Required("entry_id"): str,
        vol.Required("room_id"): str,
    }
)
@websocket_api.async_response
@_handle
async def ws_room_delete(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Remove a room (its entities and devices go with it)."""
    entry = _entry(hass, msg["entry_id"])
    sub = _room(entry, msg["room_id"])
    hass.config_entries.async_remove_subentry(entry, sub.subentry_id)
    connection.send_result(msg["id"])


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "tidy_rooms/room/reorder",
        vol.Required("entry_id"): str,
        vol.Required("order"): [str],
    }
)
@websocket_api.async_response
@_handle
async def ws_room_reorder(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Change the room priority (no reload: see __init__)."""
    entry = _entry(hass, msg["entry_id"])
    rooms = {
        sid for sid, sub in entry.subentries.items() if sub.subentry_type == SUBENTRY_ROOM
    }
    order = msg["order"]
    if set(order) != rooms or len(order) != len(rooms):
        raise _Error("invalid_order", "The order must list every room once")
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_ROOM_ORDER: order}
    )
    connection.send_result(msg["id"])


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "tidy_rooms/room/set_enabled",
        vol.Required("entry_id"): str,
        vol.Required("room_id"): str,
        vol.Required("enabled"): bool,
    }
)
@websocket_api.async_response
@_handle
async def ws_room_set_enabled(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Include or skip a room."""
    engine = _engine(hass, msg["entry_id"])
    if msg["room_id"] not in engine.rooms:
        raise _Error(ERR_NOT_FOUND, "Unknown room")
    await engine.async_set_room_enabled(msg["room_id"], msg["enabled"])
    connection.send_result(msg["id"])


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "tidy_rooms/settings/save",
        vol.Required("entry_id"): str,
        vol.Required("data"): dict,
    }
)
@websocket_api.async_response
@_handle
async def ws_settings_save(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Save the global settings (fields left out are cleared)."""
    entry = _entry(hass, msg["entry_id"])
    sections = settings_sections(hass, entry, msg["data"].get(CONF_WORK_MODE_ENTITY))
    schema = vol.Schema({k: v for s in sections.values() for k, v in s.schema.items()})
    try:
        data = schema(msg["data"])
    except vol.Invalid as err:
        connection.send_result(msg["id"], {"errors": _field_errors(err)})
        return
    keys = settings_keys()
    options = {k: v for k, v in entry.options.items() if k not in keys}
    hass.config_entries.async_update_entry(entry, options={**options, **data})
    connection.send_result(msg["id"], {})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "tidy_rooms/set_enabled",
        vol.Required("entry_id"): str,
        vol.Required("enabled"): bool,
    }
)
@websocket_api.async_response
@_handle
async def ws_set_enabled(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Pause or resume automatic cleaning."""
    await _engine(hass, msg["entry_id"]).async_set_enabled(msg["enabled"])
    connection.send_result(msg["id"])


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "tidy_rooms/clean_now",
        vol.Required("entry_id"): str,
        vol.Required("room_id"): str,
        # Absent: the next pass's work mode. None: leave the robot's mode.
        vol.Optional("work_mode"): vol.Any(str, None),
    }
)
@websocket_api.async_response
@_handle
async def ws_clean_now(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Clean a room now, even if someone is there."""
    engine = _engine(hass, msg["entry_id"])
    if msg["room_id"] not in engine.rooms:
        raise _Error(ERR_NOT_FOUND, "Unknown room")
    if "work_mode" in msg:
        await engine.async_clean_now(
            msg["room_id"], msg["work_mode"], use_default=False
        )
    else:
        await engine.async_clean_now(msg["room_id"])
    connection.send_result(msg["id"])


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): "tidy_rooms/stop_job", vol.Required("entry_id"): str}
)
@websocket_api.async_response
@_handle
async def ws_stop_job(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Stop the current job and send the robot home."""
    await _engine(hass, msg["entry_id"]).async_stop_job()
    connection.send_result(msg["id"])
