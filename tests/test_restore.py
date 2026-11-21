"""Putting the robot's work mode and fan speed back after Tidy Rooms' jobs."""

from __future__ import annotations

from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import EVENT_CALL_SERVICE
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import area_registry as ar

from custom_components.tidy_rooms.const import CONF_JOB_ENTITY, CONF_RESTORE_SETTINGS

from .test_init import MODE, SENSOR, VACUUM, advance, make

MODES = {"options": ["vacuum", "mop_after_vacuum", "mop"]}
SPEEDS = ["quiet", "normal", "max"]
JOB = "binary_sensor.robot_cleaning_job"


def robot(hass: HomeAssistant, state: str, fan: str) -> None:
    hass.states.async_set(VACUUM, state, {"fan_speed_list": SPEEDS, "fan_speed": fan})


def mode(hass: HomeAssistant, option: str) -> None:
    hass.states.async_set(MODE, option, MODES)


async def start(hass: HomeAssistant, freezer: FrozenDateTimeFactory, **options: Any):
    """The robot on vacuum/quiet; the kitchen's first pass starts at 10:11."""
    robot(hass, "docked", "quiet")
    mode(hass, "vacuum")
    entry, _, calls = await make(
        hass, freezer, options={CONF_RESTORE_SETTINGS: True, **options}
    )
    robot(hass, "docked", "quiet")
    mode(hass, "vacuum")
    await advance(hass, freezer, 11)
    assert len(calls["clean_area"]) == 1
    # The robot takes the settings of the job.
    mode(hass, "mop_after_vacuum")
    robot(hass, "cleaning", "normal")
    await advance(hass, freezer, 10)
    return entry, calls


async def finish(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, fan="normal"
) -> None:
    robot(hass, "docked", fan)
    await advance(hass, freezer, 6)


async def test_off_by_default(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry, _, calls = await make(hass, freezer)
    assert entry.runtime_data.restore_settings is False
    await advance(hass, freezer, 11)
    hass.states.async_set(VACUUM, "cleaning")
    await advance(hass, freezer, 10)
    hass.states.async_set(VACUUM, "docked")
    await advance(hass, freezer, 20)
    assert [c.data["option"] for c in calls["mode"]] == ["mop_after_vacuum"]


async def test_settings_put_back_and_confirmed(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry, calls = await start(hass, freezer)
    await finish(hass, freezer)
    assert calls["mode"][-1].data["option"] == "vacuum"
    assert calls["fan"][-1].data["fan_speed"] == "quiet"
    # The robot reports them: confirmed, nothing more is sent.
    mode(hass, "vacuum")
    robot(hass, "docked", "quiet")
    sent = len(calls["mode"]) + len(calls["fan"])
    await advance(hass, freezer, 10)
    assert len(calls["mode"]) + len(calls["fan"]) == sent
    assert entry.runtime_data.robot_restore is None


async def test_lost_command_is_retried_then_given_up(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry, calls = await start(hass, freezer)
    await finish(hass, freezer)
    restores = [c for c in calls["mode"] if c.data["option"] == "vacuum"]
    assert len(restores) == 1
    # The robot never takes them (at the dock it sometimes does not answer).
    await advance(hass, freezer, 10)
    restores = [c for c in calls["mode"] if c.data["option"] == "vacuum"]
    assert len(restores) == 3
    assert entry.runtime_data.robot_restore is None


async def test_settings_changed_by_someone_else_are_left_alone(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    _, calls = await start(hass, freezer)
    mode(hass, "mop")  # changed in the app during the job
    await finish(hass, freezer)
    assert calls["mode"][-1].data["option"] == "mop_after_vacuum"  # not restored
    assert calls["fan"][-1].data["fan_speed"] == "quiet"  # still ours: restored


async def test_waits_for_a_job_started_elsewhere(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    hass.states.async_set(JOB, "off")
    _, calls = await start(hass, freezer, **{CONF_JOB_ENTITY: JOB})
    hass.states.async_set(JOB, "on")
    await advance(hass, freezer, 1)
    hass.states.async_set(JOB, "off")  # our job ends...
    robot(hass, "docked", "normal")
    await advance(hass, freezer, 1)
    assert calls["mode"][-1].data["option"] == "vacuum"

    # ...and with an app job running right after, nothing is sent until it ends.
    count = len(calls["mode"])
    hass.states.async_set(JOB, "on")
    mode(hass, "mop_after_vacuum")
    await advance(hass, freezer, 5)
    assert len(calls["mode"]) == count


async def test_after_an_interruption_restore_follows_return_home(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    order: list[str] = []

    @callback  # in the event loop, in order (a plain function runs in a thread)
    def record(event: Event) -> None:
        order.append(f"{event.data['domain']}.{event.data['service']}")

    _, _ = await start(hass, freezer)
    hass.bus.async_listen(EVENT_CALL_SERVICE, record)
    hass.states.async_set(SENSOR, "on")  # someone walks in
    await hass.async_block_till_done()
    robot(hass, "returning", "normal")
    await advance(hass, freezer, 1)
    assert order == ["vacuum.return_to_base"]  # not docked yet: no restore
    robot(hass, "docked", "normal")
    await advance(hass, freezer, 1)
    assert order == [
        "vacuum.return_to_base",
        "select.select_option",
        "vacuum.set_fan_speed",
    ]


async def test_jobs_in_a_row_restore_once_at_the_end(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Between two jobs nothing is restored; at the end, the first settings."""
    robot(hass, "docked", "quiet")
    mode(hass, "vacuum")
    entry, _, calls = await make(hass, freezer, options={CONF_RESTORE_SETTINGS: True})
    await entry.runtime_data.async_set_enabled(False)
    hall = ar.async_get(hass).async_create("Hall")
    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            data={  # type: ignore[arg-type]
                "area": hall.id,
                "empty_minutes": 0,
                "passes": [{"id": "h1", "forced": True, "work_mode": "mop"}],
            },
            subentry_type="room",
            title="Hall",
            unique_id=hall.id,
        ),
    )
    await hass.async_block_till_done()  # reloaded
    robot(hass, "docked", "quiet")
    mode(hass, "vacuum")
    await entry.runtime_data.async_set_enabled(True)
    await hass.async_block_till_done()
    assert calls["mode"][-1].data["option"] == "mop"  # the hall: always free
    mode(hass, "mop")
    robot(hass, "cleaning", "normal")
    await advance(hass, freezer, 12)

    await finish(hass, freezer)  # the kitchen is free by now: it goes next
    options = [c.data["option"] for c in calls["mode"]]
    assert options[-1] == "mop_after_vacuum" and "vacuum" not in options
    mode(hass, "mop_after_vacuum")
    robot(hass, "cleaning", "normal")
    await advance(hass, freezer, 10)

    await finish(hass, freezer)
    assert calls["mode"][-1].data["option"] == "vacuum"
    assert calls["fan"][-1].data["fan_speed"] == "quiet"
