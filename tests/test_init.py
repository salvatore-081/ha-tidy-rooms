"""End-to-end tests with a fake robot vacuum."""

from __future__ import annotations

from datetime import timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.tidy_rooms.const import (
    CONF_AREA,
    CONF_CLEAN_ACTION,
    CONF_EMPTY_MINUTES,
    CONF_FULL_DEADLINE,
    CONF_FULL_MODE_OPTION,
    CONF_FULL_PER_DAY,
    CONF_JOB_DONE_DELAY,
    CONF_JOB_ENTITY,
    CONF_MIN_BATTERY,
    CONF_MIN_GAP_HOURS,
    CONF_NORMAL_FAN_SPEED,
    CONF_OCCUPANCY_SENSORS,
    CONF_QUIET_END,
    CONF_QUIET_FAN_SPEED,
    CONF_QUIET_START,
    CONF_START_TIMEOUT,
    CONF_VACUUM,
    CONF_VACUUM_DEADLINE,
    CONF_VACUUM_MODE_OPTION,
    CONF_VACUUM_PER_DAY,
    CONF_WORK_MODE_ENTITY,
    DOMAIN,
    SUBENTRY_ROOM,
)

VACUUM = "vacuum.robot"
SENSOR = "binary_sensor.kitchen_presence"
MODE = "select.robot_work_mode"


@pytest.fixture
async def setup(hass: HomeAssistant, freezer: FrozenDateTimeFactory):
    """A robot, a kitchen with a presence sensor, and the integration."""
    return await make(hass, freezer)


async def make(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    options: dict | None = None,
    **room_extra,
):
    """Set up the integration with one room."""
    await hass.config.async_set_time_zone("Europe/Rome")
    freezer.move_to("2026-01-12 10:00:00+01:00")  # Monday 10:00
    area = ar.async_get(hass).async_create("Kitchen")
    hass.states.async_set(VACUUM, "docked", {"fan_speed_list": ["quiet", "normal"]})
    hass.states.async_set(MODE, "vacuum", {"options": ["vacuum", "mop_after_vacuum"]})
    hass.states.async_set(SENSOR, "off")

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Robot",
        data={CONF_VACUUM: VACUUM},
        options={
            CONF_QUIET_START: "22:30:00",
            CONF_QUIET_END: "08:00:00",
            CONF_MIN_BATTERY: 0,
            CONF_START_TIMEOUT: 3,
            CONF_JOB_DONE_DELAY: 5,
            CONF_WORK_MODE_ENTITY: MODE,
            CONF_FULL_MODE_OPTION: "mop_after_vacuum",
            CONF_VACUUM_MODE_OPTION: "vacuum",
            CONF_NORMAL_FAN_SPEED: "normal",
            CONF_QUIET_FAN_SPEED: "quiet",
            **(options or {}),
        },
        subentries_data=[
            ConfigSubentryData(
                subentry_type=SUBENTRY_ROOM,
                title="Kitchen",
                unique_id=area.id,
                data={
                    CONF_AREA: area.id,
                    CONF_OCCUPANCY_SENSORS: [SENSOR],
                    CONF_EMPTY_MINUTES: 10,
                    CONF_FULL_PER_DAY: 1,
                    CONF_VACUUM_PER_DAY: 2,
                    CONF_MIN_GAP_HOURS: 6,
                    CONF_FULL_DEADLINE: "19:00:00",
                    CONF_VACUUM_DEADLINE: "21:30:00",
                    **room_extra,
                },
            )
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    # After setup: the real vacuum component would replace these services.
    calls = {
        "clean_area": async_mock_service(hass, "vacuum", "clean_area"),
        "fan": async_mock_service(hass, "vacuum", "set_fan_speed"),
        "home": async_mock_service(hass, "vacuum", "return_to_base"),
        "mode": async_mock_service(hass, "select", "select_option"),
    }
    return entry, area, calls


def status(hass: HomeAssistant) -> str:
    states = [s for s in hass.states.async_all("sensor") if s.entity_id.endswith("_status")]
    assert len(states) == 1
    return states[0].state


async def advance(hass: HomeAssistant, freezer: FrozenDateTimeFactory, minutes: int) -> None:
    for _ in range(minutes):
        freezer.tick(timedelta(minutes=1))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()


async def test_full_day(hass: HomeAssistant, freezer: FrozenDateTimeFactory, setup) -> None:
    """Empty kitchen: full pass now, second vacuum after the gap."""
    _, area, calls = setup
    # The sensor went off at 10:00: the room is free after 10 minutes.
    await advance(hass, freezer, 11)
    assert len(calls["clean_area"]) == 1
    assert calls["clean_area"][0].data["cleaning_area_id"] == [area.id]
    assert calls["mode"][-1].data["option"] == "mop_after_vacuum"
    assert calls["fan"][-1].data["fan_speed"] == "normal"

    # Robot runs, comes back for a mop wash, runs again, then docks for good.
    hass.states.async_set(VACUUM, "cleaning")
    await advance(hass, freezer, 15)
    hass.states.async_set(VACUUM, "docked")
    await advance(hass, freezer, 2)
    hass.states.async_set(VACUUM, "cleaning")
    await advance(hass, freezer, 10)
    hass.states.async_set(VACUUM, "returning")
    hass.states.async_set(VACUUM, "docked")
    await advance(hass, freezer, 4)
    assert status(hass) == "cleaning"
    await advance(hass, freezer, 2)
    assert status(hass) == "waiting_gap"
    assert len(calls["clean_area"]) == 1

    # Six hours later the second (vacuum only) pass starts.
    await advance(hass, freezer, 6 * 60)
    assert len(calls["clean_area"]) == 2
    assert calls["mode"][-1].data["option"] == "vacuum"


async def test_interrupt_when_someone_enters(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, setup
) -> None:
    """Someone walks in: robot goes home and the room stays due."""
    _, _, calls = setup
    await advance(hass, freezer, 11)
    hass.states.async_set(VACUUM, "cleaning")
    await hass.async_block_till_done()
    hass.states.async_set(SENSOR, "on")
    await hass.async_block_till_done()
    assert len(calls["home"]) == 1
    assert status(hass) == "waiting_occupied"


async def test_retry_when_robot_does_not_start(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, setup
) -> None:
    """No reaction from the robot: retry, then give up for a while."""
    _, _, calls = setup
    await advance(hass, freezer, 11)
    assert len(calls["clean_area"]) == 1
    await advance(hass, freezer, 3)
    assert len(calls["clean_area"]) == 2
    await advance(hass, freezer, 3)
    assert len(calls["clean_area"]) == 3
    await advance(hass, freezer, 3)
    assert len(calls["clean_area"]) == 3  # gave up
    await advance(hass, freezer, 16)
    assert len(calls["clean_area"]) == 4  # cooldown over


async def test_forced_and_quiet_after_deadline(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, setup
) -> None:
    """Kitchen busy all day: cleaned at the deadline with the quiet fan."""
    _, _, calls = setup
    hass.states.async_set(SENSOR, "on")
    await advance(hass, freezer, 60)
    assert calls["clean_area"] == []
    freezer.move_to("2026-01-12 18:59:30+01:00")
    await advance(hass, freezer, 1)
    assert len(calls["clean_area"]) == 1
    assert calls["fan"][-1].data["fan_speed"] == "quiet"


async def test_custom_clean_action(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """The room's custom action replaces clean_area, with templates rendered."""
    action = [
        {
            "action": "vacuum.send_command",
            "target": {"entity_id": "{{ vacuum_entity }}"},
            "data": {
                "command": "clean_V2",
                "params": {
                    "act": "start",
                    "content": {"type": "freeClean", "value": "1,2"},
                },
            },
        }
    ]
    _, _, calls = await make(hass, freezer, **{CONF_CLEAN_ACTION: action})
    send = async_mock_service(hass, "vacuum", "send_command")
    await advance(hass, freezer, 11)
    assert calls["clean_area"] == []
    assert len(send) == 1
    assert send[0].data["entity_id"] == [VACUUM]
    assert send[0].data["command"] == "clean_V2"
    assert send[0].data["params"] == {
        "act": "start",
        "content": {"type": "freeClean", "value": "1,2"},
    }
    # Work mode and fan speed are still set first.
    assert calls["mode"][-1].data["option"] == "mop_after_vacuum"


async def test_invalid_clean_action_disables_room(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A broken custom action never falls back to clean_area."""
    _, _, calls = await make(hass, freezer, **{CONF_CLEAN_ACTION: [{"nonsense": 1}]})
    await advance(hass, freezer, 11)
    assert calls["clean_area"] == []
    assert status(hass) == "disabled"


async def test_job_gives_up_after_max_duration(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, setup
) -> None:
    """A job stuck in pause does not block the plan forever."""
    _, _, calls = setup
    await advance(hass, freezer, 11)
    hass.states.async_set(VACUUM, "cleaning")
    await advance(hass, freezer, 5)
    hass.states.async_set(VACUUM, "paused")
    await advance(hass, freezer, 170)
    assert status(hass) == "cleaning"
    await advance(hass, freezer, 10)
    assert status(hass) != "cleaning"


JOB = "binary_sensor.robot_cleaning_job"


async def test_job_entity_decides_the_end(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Long stops at the dock do not end the job; the job sensor does."""
    hass.states.async_set(JOB, "off")
    _, _, calls = await make(hass, freezer, options={CONF_JOB_ENTITY: JOB})
    await advance(hass, freezer, 11)
    assert len(calls["clean_area"]) == 1

    hass.states.async_set(VACUUM, "cleaning")
    hass.states.async_set(JOB, "on")
    await advance(hass, freezer, 10)
    # Back at the dock to wash the mop, much longer than the docked delay.
    hass.states.async_set(VACUUM, "docked")
    await advance(hass, freezer, 20)
    assert status(hass) == "cleaning"
    hass.states.async_set(VACUUM, "cleaning")
    await advance(hass, freezer, 10)
    hass.states.async_set(VACUUM, "returning")
    hass.states.async_set(JOB, "off")
    await hass.async_block_till_done()
    assert status(hass) == "waiting_gap"


async def test_job_started_elsewhere_keeps_robot_busy(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A job from the app keeps the robot busy even while docked."""
    hass.states.async_set(JOB, "on")
    _, _, calls = await make(hass, freezer, options={CONF_JOB_ENTITY: JOB})
    await advance(hass, freezer, 11)
    assert calls["clean_area"] == []
    assert status(hass) == "waiting_robot"
    hass.states.async_set(JOB, "off")
    await advance(hass, freezer, 1)
    assert len(calls["clean_area"]) == 1


async def test_room_devices_hang_from_the_robot(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, setup
) -> None:
    """Room devices are linked to the robot device by its registry id."""
    from homeassistant.helpers import device_registry as dr

    entry, _, _ = setup
    reg = dr.async_get(hass)
    robot = reg.async_get_device_by_identifier((DOMAIN, entry.entry_id), entry.entry_id)
    room_id = next(iter(entry.subentries))
    room = reg.async_get_device_by_identifier((DOMAIN, room_id), entry.entry_id)
    assert robot is not None and room is not None
    assert room.via_device_id == robot.id


async def test_room_fan_speed_and_modes(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """The room's own fan speed and work modes replace the global ones."""
    _, _, calls = await make(
        hass,
        freezer,
        fan_speed="quiet",
        full_mode="vacuum",
        vacuum_mode="mop_after_vacuum",
    )
    await advance(hass, freezer, 11)
    assert len(calls["clean_area"]) == 1
    assert calls["fan"][-1].data["fan_speed"] == "quiet"
    assert calls["mode"][-1].data["option"] == "vacuum"  # room's full mode


async def test_room_empty_settings_fall_back_to_global(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Without room settings the global ones apply."""
    _, _, calls = await make(hass, freezer, fan_speed="", full_mode=None)
    await advance(hass, freezer, 11)
    assert calls["fan"][-1].data["fan_speed"] == "normal"
    assert calls["mode"][-1].data["option"] == "mop_after_vacuum"


async def test_quiet_wins_over_room_fan_speed(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Forced while someone is there: the quiet speed, not the room's."""
    hass.states.async_set(VACUUM, "docked", {"fan_speed_list": ["quiet", "normal", "max"]})
    _, _, calls = await make(hass, freezer, fan_speed="max")
    hass.states.async_set(VACUUM, "docked", {"fan_speed_list": ["quiet", "normal", "max"]})
    hass.states.async_set(SENSOR, "on")
    freezer.move_to("2026-01-12 18:59:30+01:00")
    await advance(hass, freezer, 1)
    assert len(calls["clean_area"]) == 1
    assert calls["fan"][-1].data["fan_speed"] == "quiet"
