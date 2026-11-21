"""Tests for the config, options and room flows."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import area_registry as ar

from custom_components.tidy_rooms.const import (
    CONF_AREA,
    CONF_EMPTY_MINUTES,
    CONF_JOB_DONE_DELAY,
    CONF_MIN_BATTERY,
    CONF_NORMAL_FAN_SPEED,
    CONF_OCCUPANCY_SENSORS,
    CONF_PASSES,
    CONF_PROXY_SENSORS,
    CONF_QUIET_FAN_SPEED,
    CONF_START_TIMEOUT,
    CONF_VACUUM,
    CONF_WAKE_MINUTES,
    CONF_WORK_MODE_ENTITY,
    DOMAIN,
    SUBENTRY_ROOM,
)

VACUUM = "vacuum.robot"


async def _create(hass: HomeAssistant):
    hass.states.async_set(
        VACUUM, "docked", {"friendly_name": "Robot", "fan_speed_list": ["quiet", "max"]}
    )
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_VACUUM: VACUUM}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Robot"
    return result["result"]


async def test_create_and_no_duplicates(hass: HomeAssistant) -> None:
    await _create(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_VACUUM: VACUUM}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


ROOM = {CONF_EMPTY_MINUTES: 10}


async def test_room_subentry(hass: HomeAssistant) -> None:
    entry = await _create(hass)
    kitchen = ar.async_get(hass).async_create("Kitchen")

    async def add(data):
        result = await hass.config_entries.subentries.async_init(
            (entry.entry_id, SUBENTRY_ROOM), context={"source": SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        return await hass.config_entries.subentries.async_configure(result["flow_id"], data)

    result = await add(
        {
            **ROOM,
            CONF_AREA: kitchen.id,
            CONF_OCCUPANCY_SENSORS: ["binary_sensor.a"],
            CONF_PROXY_SENSORS: ["binary_sensor.b"],
        }
    )
    assert result["errors"] == {CONF_PROXY_SENSORS: "proxy_with_occupancy"}

    result = await add({**ROOM, CONF_AREA: kitchen.id})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Kitchen"
    # The program is set in the panel: it starts empty.
    subentry = next(iter(entry.subentries.values()))
    assert subentry.data[CONF_PASSES] == []

    result = await add({**ROOM, CONF_AREA: kitchen.id})
    assert result["errors"] == {CONF_AREA: "area_already_configured"}

    # Edit the room: the program set in the panel is kept.
    program = [{"id": "a1", "forced": True, "end": "12:00:00"}]
    hass.config_entries.async_update_subentry(
        entry, subentry, data={**subentry.data, CONF_PASSES: program}
    )
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_ROOM),
        context={"source": "reconfigure", "subentry_id": subentry.subentry_id},
    )
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**ROOM, CONF_AREA: kitchen.id, CONF_EMPTY_MINUTES: 20}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    data = entry.subentries[subentry.subentry_id].data
    assert data[CONF_EMPTY_MINUTES] == 20
    assert data[CONF_PASSES] == program


async def test_options(hass: HomeAssistant) -> None:
    entry = await _create(hass)
    hass.states.async_set("select.mode", "vacuum", {"options": ["vacuum", "mop"]})
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_WAKE_MINUTES: 15,
            CONF_WORK_MODE_ENTITY: "select.mode",
            CONF_START_TIMEOUT: 3,
            CONF_JOB_DONE_DELAY: 5,
        },
    )
    assert result["step_id"] == "robot"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_MIN_BATTERY: 30, CONF_NORMAL_FAN_SPEED: "max", CONF_QUIET_FAN_SPEED: "quiet"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_QUIET_FAN_SPEED] == "quiet"
    assert entry.options[CONF_MIN_BATTERY] == 30
    assert entry.options[CONF_WORK_MODE_ENTITY] == "select.mode"
