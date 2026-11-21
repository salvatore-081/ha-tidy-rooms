"""Tests for the WebSocket API of the panel, the job log and reloads."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.tidy_rooms import panel
from custom_components.tidy_rooms.const import (
    CONF_AREA,
    CONF_EMPTY_MINUTES,
    CONF_FULL_PER_DAY,
    CONF_MIN_GAP_HOURS,
    CONF_OCCUPANCY_SENSORS,
    CONF_QUIET_FAN_SPEED,
    CONF_ROOM_ORDER,
    CONF_VACUUM_PER_DAY,
    CONF_WORK_MODE_ENTITY,
    SUBENTRY_ROOM,
)

from .test_init import SENSOR, VACUUM, advance, make


async def _ws(hass_ws_client: WebSocketGenerator, hass: HomeAssistant, token=None):
    return await hass_ws_client(hass, token) if token else await hass_ws_client(hass)


async def _call(client, **msg):
    await client.send_json_auto_id(msg)
    return await client.receive_json()


async def test_entries_and_snapshot(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, hass_ws_client
) -> None:
    client = await _ws(hass_ws_client, hass)
    entry, _, _ = await make(hass, freezer)

    res = await _call(client, type="tidy_rooms/entries")
    assert res["result"] == [
        {"entry_id": entry.entry_id, "title": "Robot", "vacuum": VACUUM, "loaded": True}
    ]

    res = await _call(client, type="tidy_rooms/subscribe", entry_id=entry.entry_id)
    assert res["success"]
    event = (await client.receive_json())["event"]
    assert event["loaded"] is True
    assert event["robot"]["entity_id"] == VACUUM
    assert event["job"] is None
    (room,) = event["rooms"]
    assert room["name"] == "Kitchen"
    assert room["status"] == "waiting_occupied"
    assert room["outlook"]["kind"] == "full"
    assert room["outlook"]["reason"] == "empty"
    assert room["outlook"]["earliest"].startswith("2026-01-12T10:10")
    assert event["next_room"] == room["id"]

    # A change of the presence sensor sends a new snapshot.
    hass.states.async_set(SENSOR, "on")
    await hass.async_block_till_done()
    freezer.tick(1)
    await advance(hass, freezer, 1)
    event = (await client.receive_json())["event"]
    assert event["rooms"][0]["occupied"] is True


async def test_unknown_entry(hass: HomeAssistant, freezer, hass_ws_client) -> None:
    client = await _ws(hass_ws_client, hass)
    await make(hass, freezer)
    res = await _call(client, type="tidy_rooms/subscribe", entry_id="nope")
    assert res["error"]["code"] == "not_found"


async def test_room_schema_and_save(hass: HomeAssistant, freezer, hass_ws_client) -> None:
    client = await _ws(hass_ws_client, hass)
    entry, kitchen, _ = await make(hass, freezer)

    res = await _call(client, type="tidy_rooms/schema", entry_id=entry.entry_id, form="room")
    names = [f["name"] for f in res["result"]["schema"]]
    assert names[0] == "area" and "clean_action" in names
    assert res["result"]["values"][CONF_EMPTY_MINUTES] == 10

    room_id = next(iter(entry.subentries))
    res = await _call(
        client,
        type="tidy_rooms/schema",
        entry_id=entry.entry_id,
        form="room",
        room_id=room_id,
    )
    assert res["result"]["values"][CONF_AREA] == kitchen.id

    living = ar.async_get(hass).async_create("Living")
    data = {
        CONF_AREA: living.id,
        CONF_OCCUPANCY_SENSORS: ["binary_sensor.living"],
        CONF_EMPTY_MINUTES: 5,
        CONF_FULL_PER_DAY: 1,
        CONF_VACUUM_PER_DAY: 1,
        CONF_MIN_GAP_HOURS: 6,
    }
    # Same area as the kitchen: rejected with a field error.
    res = await _call(
        client,
        type="tidy_rooms/room/save",
        entry_id=entry.entry_id,
        data={**data, CONF_AREA: kitchen.id},
    )
    assert res["result"] == {"errors": {CONF_AREA: "area_already_configured"}}
    # Out of range: rejected by the schema.
    res = await _call(
        client,
        type="tidy_rooms/room/save",
        entry_id=entry.entry_id,
        data={**data, CONF_FULL_PER_DAY: 9},
    )
    assert res["result"] == {"errors": {CONF_FULL_PER_DAY: "invalid"}}

    res = await _call(client, type="tidy_rooms/room/save", entry_id=entry.entry_id, data=data)
    new_id = res["result"]["room_id"]
    await hass.async_block_till_done()
    sub = entry.subentries[new_id]
    assert sub.title == "Living" and sub.subentry_type == SUBENTRY_ROOM
    assert set(entry.runtime_data.rooms) == {room_id, new_id}

    # Edit, then delete.
    res = await _call(
        client,
        type="tidy_rooms/room/save",
        entry_id=entry.entry_id,
        room_id=new_id,
        data={**data, CONF_EMPTY_MINUTES: 20},
    )
    assert res["result"] == {"room_id": new_id}
    await hass.async_block_till_done()
    assert entry.runtime_data.rooms[new_id].config.empty_minutes == 20

    res = await _call(
        client, type="tidy_rooms/room/delete", entry_id=entry.entry_id, room_id=new_id
    )
    assert res["success"]
    await hass.async_block_till_done()
    assert set(entry.runtime_data.rooms) == {room_id}


async def test_reorder_without_reload(hass: HomeAssistant, freezer, hass_ws_client) -> None:
    client = await _ws(hass_ws_client, hass)
    entry, _, _ = await make(hass, freezer)
    living = ar.async_get(hass).async_create("Living")
    res = await _call(
        client,
        type="tidy_rooms/room/save",
        entry_id=entry.entry_id,
        data={
            CONF_AREA: living.id,
            CONF_EMPTY_MINUTES: 5,
            CONF_FULL_PER_DAY: 1,
            CONF_VACUUM_PER_DAY: 1,
            CONF_MIN_GAP_HOURS: 6,
        },
    )
    new_id = res["result"]["room_id"]
    await hass.async_block_till_done()
    kitchen_id = next(s for s in entry.subentries if s != new_id)
    engine = entry.runtime_data
    assert list(engine.rooms) == [kitchen_id, new_id]

    res = await _call(
        client, type="tidy_rooms/room/reorder", entry_id=entry.entry_id, order=[new_id]
    )
    assert res["error"]["code"] == "invalid_order"

    res = await _call(
        client,
        type="tidy_rooms/room/reorder",
        entry_id=entry.entry_id,
        order=[new_id, kitchen_id],
    )
    assert res["success"]
    await hass.async_block_till_done()
    assert entry.runtime_data is engine  # not reloaded
    assert list(engine.rooms) == [new_id, kitchen_id]
    assert entry.options[CONF_ROOM_ORDER] == [new_id, kitchen_id]


async def test_settings(hass: HomeAssistant, freezer, hass_ws_client) -> None:
    client = await _ws(hass_ws_client, hass)
    entry, _, _ = await make(hass, freezer)
    res = await _call(client, type="tidy_rooms/schema", entry_id=entry.entry_id, form="settings")
    sections = res["result"]["sections"]
    assert set(sections) == {"schedule", "wake", "signals", "robot"}
    robot = [f["name"] for f in sections["robot"]]
    assert robot == [
        "normal_fan_speed",
        "quiet_fan_speed",
        "full_mode_option",
        "vacuum_mode_option",
    ]
    values = res["result"]["values"]
    assert values[CONF_QUIET_FAN_SPEED] == "quiet"

    # Without a work mode entity there are no work mode fields.
    res = await _call(
        client,
        type="tidy_rooms/schema",
        entry_id=entry.entry_id,
        form="settings",
        work_mode_entity=None,
    )
    assert [f["name"] for f in res["result"]["sections"]["robot"]] == robot[:2]

    engine = entry.runtime_data
    new = {**values, "min_battery": 40, "wake_minutes": 15}
    new.pop(CONF_WORK_MODE_ENTITY)
    new.pop("full_mode_option")
    new.pop("vacuum_mode_option")
    res = await _call(client, type="tidy_rooms/settings/save", entry_id=entry.entry_id, data=new)
    assert res["result"] == {}
    await hass.async_block_till_done()
    assert entry.options["min_battery"] == 40
    assert CONF_WORK_MODE_ENTITY not in entry.options
    assert entry.runtime_data is not engine  # reloaded

    res = await _call(
        client,
        type="tidy_rooms/settings/save",
        entry_id=entry.entry_id,
        data={**new, "min_battery": 400},
    )
    assert res["result"] == {"errors": {"min_battery": "invalid"}}


async def test_commands_and_history(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, hass_ws_client
) -> None:
    client = await _ws(hass_ws_client, hass)
    entry, _, calls = await make(hass, freezer)
    engine = entry.runtime_data
    room_id = next(iter(engine.rooms))

    res = await _call(client, type="tidy_rooms/set_enabled", entry_id=entry.entry_id, enabled=False)
    assert res["success"] and engine.enabled is False
    await advance(hass, freezer, 11)
    assert calls["clean_area"] == []

    res = await _call(
        client,
        type="tidy_rooms/room/set_enabled",
        entry_id=entry.entry_id,
        room_id=room_id,
        enabled=False,
    )
    assert res["success"] and engine.rooms[room_id].state.enabled is False

    res = await _call(
        client,
        type="tidy_rooms/clean_now",
        entry_id=entry.entry_id,
        room_id=room_id,
        kind="vacuum",
    )
    assert res["success"]
    await hass.async_block_till_done()
    assert len(calls["clean_area"]) == 1
    assert engine.job is not None and engine.job.manual

    res = await _call(
        client, type="tidy_rooms/clean_now", entry_id=entry.entry_id, room_id=room_id
    )
    assert res["error"]["code"] == "robot_busy"

    res = await _call(client, type="tidy_rooms/stop_job", entry_id=entry.entry_id)
    assert res["success"]
    await hass.async_block_till_done()
    assert engine.job is None
    assert len(calls["home"]) == 1

    res = await _call(client, type="tidy_rooms/history", entry_id=entry.entry_id)
    (job,) = res["result"]["jobs"]
    assert job["room"] == "Kitchen"
    assert job["kind"] == "vacuum"
    assert job["manual"] is True
    assert job["result"] == "stopped"


async def test_read_only_user(
    hass: HomeAssistant, freezer, hass_ws_client, hass_read_only_access_token
) -> None:
    client = await _ws(hass_ws_client, hass, hass_read_only_access_token)
    entry, _, _ = await make(hass, freezer)
    res = await _call(client, type="tidy_rooms/subscribe", entry_id=entry.entry_id)
    assert res["success"]  # the card works for every user
    await client.receive_json()
    res = await _call(client, type="tidy_rooms/set_enabled", entry_id=entry.entry_id, enabled=False)
    assert res["error"]["code"] == "unauthorized"
    res = await _call(client, type="tidy_rooms/schema", entry_id=entry.entry_id, form="room")
    assert res["error"]["code"] == "unauthorized"


async def test_history_is_kept_30_days(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry, _, _ = await make(hass, freezer)
    engine = entry.runtime_data
    await advance(hass, freezer, 11)
    hass.states.async_set(VACUUM, "cleaning")
    await advance(hass, freezer, 10)
    hass.states.async_set(VACUUM, "docked")
    await advance(hass, freezer, 6)
    (record,) = engine.history.records
    assert record.result == "done" and record.kind == "full" and not record.manual

    # Survives a reload.
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert len(entry.runtime_data.history.records) == 1

    freezer.tick(31 * 24 * 3600)
    fresh = replace(record, started=dt_util.now().isoformat())
    entry.runtime_data.history.add(fresh)  # prunes the old ones
    assert entry.runtime_data.history.records == [fresh]


async def test_running_job_survives_reload(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry, _, calls = await make(hass, freezer)
    await advance(hass, freezer, 11)
    hass.states.async_set(VACUUM, "cleaning")
    await advance(hass, freezer, 5)
    assert entry.runtime_data.job is not None

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    engine = entry.runtime_data
    assert engine.job is not None
    assert engine.job.phase.value == "running"
    assert len(calls["clean_area"]) == 1  # not sent again

    hass.states.async_set(VACUUM, "docked")
    await advance(hass, freezer, 6)
    assert engine.job is None
    assert engine.history.records[-1].result == "done"


async def test_panel_registered_once_and_removed(
    hass: HomeAssistant, freezer, tmp_path
) -> None:
    (tmp_path / panel.PANEL_FILE).write_text("")
    (tmp_path / panel.CARD_FILE).write_text("")
    hass.config.components.add("frontend")
    hass.http = MagicMock(async_register_static_paths=AsyncMock())
    with (
        patch.object(panel, "FRONTEND_DIR", tmp_path),
        patch.object(panel, "async_register_built_in_panel") as register,
        patch.object(panel, "add_extra_js_url") as add_js,
        patch.object(panel, "async_remove_panel") as remove,
        patch.object(panel, "remove_extra_js_url") as remove_js,
    ):
        entry, _, _ = await make(hass, freezer)
        await panel.async_register(hass)  # a second entry: nothing new
        assert register.call_count == 1
        kwargs = register.call_args.kwargs
        assert kwargs["frontend_url_path"] == "tidy-rooms"
        assert kwargs["require_admin"] is True
        assert kwargs["config"]["_panel_custom"]["js_url"].endswith("?v=0.2.0")
        add_js.assert_called_once()

        await hass.config_entries.async_unload(entry.entry_id)
        remove.assert_called_once_with(hass, "tidy-rooms")
        remove_js.assert_called_once()


async def test_panel_missing_js(
    hass: HomeAssistant, freezer, tmp_path, caplog: pytest.LogCaptureFixture
) -> None:
    hass.config.components.add("frontend")
    hass.http = MagicMock(async_register_static_paths=AsyncMock())
    with (
        patch.object(panel, "FRONTEND_DIR", tmp_path),
        patch.object(panel, "async_register_built_in_panel") as register,
    ):
        await make(hass, freezer)
    register.assert_not_called()
    assert "install a release" in caplog.text
