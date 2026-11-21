"""Engine tests for cleaning programs: saved state, jobs, entities."""

from __future__ import annotations

from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.tidy_rooms.const import CONF_WORK_MODE_ENTITY, DOMAIN

from .test_init import MODE, VACUUM, advance, make

ENTRY = "entry0000000000000000000000000"
ROOM = "room00000000000000000000000000"


def _stored(key: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"version": 1, "minor_version": 1, "key": key, "data": data}


def _state_0_3_0(**room: Any) -> dict[str, Any]:
    return {
        "day": "2026-01-12",
        "awake_day": "",
        "enabled": True,
        "job": None,
        "rooms": {
            ROOM: {
                "enabled": True,
                "full_today": 0,
                "vacuum_today": 0,
                "last_full": None,
                "last_vacuum": None,
                "last_result": None,
                **room,
            }
        },
    }


def _job_record_0_3_0() -> dict[str, Any]:
    return {
        "room_id": ROOM,
        "room": "Kitchen",
        "kind": "full",
        "forced": False,
        "quiet": False,
        "manual": False,
        "attempts": 1,
        "started": "2026-01-12T08:30:00+01:00",
        "ended": "2026-01-12T09:00:00+01:00",
        "result": "done",
    }


def _buttons(hass: HomeAssistant) -> dict[str, str]:
    """Unique id suffix -> entity id of the room's buttons."""
    reg = er.async_get(hass)
    return {
        e.unique_id.removeprefix(f"{ROOM}_"): e.entity_id
        for e in reg.entities.values()
        if e.platform == DOMAIN and e.domain == "button"
    }


async def test_state_and_history_saved_by_0_3_0(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, hass_storage: dict[str, Any]
) -> None:
    """Counts become passes done; old job records are kept."""
    hass_storage[f"{DOMAIN}.{ENTRY}"] = _stored(
        f"{DOMAIN}.{ENTRY}",
        _state_0_3_0(
            full_today=1,
            vacuum_today=1,
            last_full="2026-01-12T09:00:00+01:00",
            last_vacuum="2026-01-12T09:00:00+01:00",
            last_result="done",
        ),
    )
    hass_storage[f"{DOMAIN}.{ENTRY}.history"] = _stored(
        f"{DOMAIN}.{ENTRY}.history", {"jobs": [_job_record_0_3_0()]}
    )
    entry, _, _ = await make(hass, freezer, entry_id=ENTRY, room_id=ROOM)
    engine = entry.runtime_data
    st = engine.rooms[ROOM].state
    assert [d.pass_id for d in st.done_today] == ["full-1"]
    assert st.last_clean is not None and st.last_clean.hour == 9
    assert engine.last_plan.statuses[ROOM].value == "waiting_gap"
    (record,) = engine.history.records
    assert record.kind == "full" and record.work_mode is None

    await hass.config_entries.async_unload(entry.entry_id)
    saved = hass_storage[f"{DOMAIN}.{ENTRY}"]["data"]["rooms"][ROOM]
    assert saved["done_today"][0]["pass_id"] == "full-1"
    assert "full_today" not in saved
    (job,) = hass_storage[f"{DOMAIN}.{ENTRY}.history"]["data"]["jobs"]
    assert job["kind"] == "full"


async def test_job_saved_by_0_3_0_continues(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, hass_storage: dict[str, Any]
) -> None:
    """A running job saved by 0.3.0 counts as the matching converted pass."""
    state = _state_0_3_0()
    state["job"] = {
        "room_id": ROOM,
        "kind": "vacuum",
        "forced": True,
        "quiet": False,
        "phase": "running",
        "started": "2026-01-12T09:50:00+01:00",
        "created": "2026-01-12T09:50:00+01:00",
        "attempts": 1,
        "docked_since": None,
        "quiet_applied": False,
        "manual": True,
    }
    hass_storage[f"{DOMAIN}.{ENTRY}"] = _stored(f"{DOMAIN}.{ENTRY}", state)
    hass.states.async_set(VACUUM, "cleaning")
    entry, _, _ = await make(hass, freezer, entry_id=ENTRY, room_id=ROOM)
    engine = entry.runtime_data
    assert engine.job is not None
    assert engine.job.decision.pass_id == "vacuum-1"
    assert engine.job.decision.work_mode == "vacuum"

    hass.states.async_set(VACUUM, "docked")
    await advance(hass, freezer, 6)
    assert engine.job is None
    assert [d.pass_id for d in engine.rooms[ROOM].state.done_today] == ["vacuum-1"]


async def test_manual_cleaning_counts_only_when_a_pass_matches(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    hass.states.async_set(
        MODE, "vacuum", {"options": ["vacuum", "mop_after_vacuum", "mop"]}
    )
    entry, _, calls = await make(hass, freezer, room_id=ROOM)
    hass.states.async_set(
        MODE, "vacuum", {"options": ["vacuum", "mop_after_vacuum", "mop"]}
    )
    engine = entry.runtime_data
    await engine.async_set_enabled(False)

    await engine.async_clean_now(ROOM, "mop", use_default=False)
    await hass.async_block_till_done()
    assert calls["mode"][-1].data["option"] == "mop"
    assert calls["fan"][-1].data["fan_speed"] == "normal"
    assert engine.job is not None and engine.job.decision.pass_id is None
    hass.states.async_set(VACUUM, "cleaning")
    await advance(hass, freezer, 5)
    hass.states.async_set(VACUUM, "docked")
    await advance(hass, freezer, 6)
    st = engine.rooms[ROOM].state
    assert st.done_today == [] and st.last_clean is None  # no pass, no gap
    assert engine.history.records[-1].pass_id is None

    # Without a choice: the next pass (vacuum and mop).
    await engine.async_clean_now(ROOM)
    await hass.async_block_till_done()
    assert engine.job is not None and engine.job.decision.pass_id == "full-1"
    hass.states.async_set(VACUUM, "cleaning")
    await advance(hass, freezer, 5)
    hass.states.async_set(VACUUM, "docked")
    await advance(hass, freezer, 6)
    (done,) = st.done_today
    assert done.pass_id == "full-1" and done.manual
    assert st.last_clean is not None


async def test_job_ending_after_midnight_does_not_count_today(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry, _, _ = await make(hass, freezer, room_id=ROOM)
    engine = entry.runtime_data
    await engine.async_set_enabled(False)
    freezer.move_to("2026-01-12 23:50:00+01:00")
    await engine.async_clean_now(ROOM, "mop_after_vacuum", use_default=False)
    hass.states.async_set(VACUUM, "cleaning")
    await advance(hass, freezer, 15)
    hass.states.async_set(VACUUM, "docked")
    await advance(hass, freezer, 6)
    assert engine.job is None
    st = engine.rooms[ROOM].state
    assert st.done_today == []
    assert st.last_clean is not None and st.last_clean.day == 13


async def test_robot_error_pauses_the_plan(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    _, _, calls = await make(hass, freezer, room_id=ROOM)
    await advance(hass, freezer, 11)
    assert len(calls["clean_area"]) == 1
    hass.states.async_set(VACUUM, "cleaning")
    await advance(hass, freezer, 2)
    hass.states.async_set(VACUUM, "error")
    await advance(hass, freezer, 1)
    hass.states.async_set(VACUUM, "docked")
    await advance(hass, freezer, 10)
    assert len(calls["clean_area"]) == 1  # paused
    await advance(hass, freezer, 6)
    assert len(calls["clean_area"]) == 2


async def test_sensors(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    entry, _, _ = await make(hass, freezer, room_id=ROOM)
    reg = er.async_get(hass)
    passes = reg.async_get_entity_id("sensor", DOMAIN, f"{ROOM}_passes_today")
    last = reg.async_get_entity_id("sensor", DOMAIN, f"{ROOM}_last_clean")
    status = reg.async_get_entity_id("sensor", DOMAIN, f"{ROOM}_status")
    assert passes and last and status
    assert hass.states.get(passes).state == "0"  # type: ignore[union-attr]
    assert hass.states.get(passes).attributes["total"] == 2  # type: ignore[union-attr]

    await advance(hass, freezer, 11)
    hass.states.async_set(VACUUM, "cleaning")
    await advance(hass, freezer, 10)
    hass.states.async_set(VACUUM, "docked")
    await advance(hass, freezer, 6)
    assert hass.states.get(passes).state == "1"  # type: ignore[union-attr]
    assert hass.states.get(last).state.startswith("2026-01-12T09:2")  # type: ignore[union-attr]
    attrs = hass.states.get(status).attributes  # type: ignore[union-attr]
    assert (attrs["passes_done"], attrs["passes_total"]) == (1, 2)
    assert attrs["next_pass"] == "vacuum"


async def test_buttons_follow_the_robot_work_modes(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry, _, calls = await make(hass, freezer, room_id=ROOM)
    buttons = _buttons(hass)
    assert set(buttons) == {
        "clean_now_mode_vacuum",
        "clean_now_mode_mop_after_vacuum",
    }
    await entry.runtime_data.async_set_enabled(False)
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": buttons["clean_now_mode_vacuum"]},
        blocking=True,
    )
    job = entry.runtime_data.job
    assert job is not None and job.decision.pass_id == "vacuum-1"
    assert calls["mode"][-1].data["option"] == "vacuum"
    await entry.runtime_data.async_stop_job()

    # The select is not there yet at startup: the buttons stay.
    hass.states.async_remove(MODE)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert set(_buttons(hass)) == set(buttons)
    assert hass.states.get(buttons["clean_now_mode_vacuum"]) is not None

    # The options are known from the entity registry, and have changed.
    reg = er.async_get(hass)
    reg.async_get_or_create(
        "select",
        "robot",
        "work_mode",
        suggested_object_id="robot_work_mode",
        capabilities={"options": ["vacuum", "mop"]},
    )
    assert reg.async_get(MODE) is not None
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert set(_buttons(hass)) == {"clean_now_mode_vacuum", "clean_now_mode_mop"}


async def test_single_button_without_work_mode_entity(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry, _, calls = await make(
        hass, freezer, options={CONF_WORK_MODE_ENTITY: None}, room_id=ROOM
    )
    (key,) = _buttons(hass)
    assert key == "clean_now"
    await entry.runtime_data.async_set_enabled(False)
    await hass.services.async_call(
        "button", "press", {"entity_id": _buttons(hass)[key]}, blocking=True
    )
    job = entry.runtime_data.job
    # Without work modes every pass matches: the first one.
    assert job is not None and job.decision.pass_id == "full-1"
    assert job.decision.work_mode is None
    assert calls["mode"] == []
