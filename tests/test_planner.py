"""Tests for the pure planner."""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest

from custom_components.tidy_rooms.planner import (
    CleanKind,
    Decision,
    GlobalConfig,
    RobotState,
    RoomConfig,
    RoomState,
    RoomStatus,
    in_window,
    plan,
    should_interrupt,
)

DAY = datetime(2026, 1, 12)  # a Monday
READY = RobotState(available=True, idle=True, battery=100)
G = GlobalConfig()


def at(hour: int, minute: int = 0) -> datetime:
    return DAY.replace(hour=hour, minute=minute)


def sensor_room(room_id: str = "living", **kw) -> RoomConfig:
    return RoomConfig(room_id, room_id, occupancy_sensors=("binary_sensor.x",), **kw)


def empty_for(minutes: int, now: datetime) -> RoomState:
    return RoomState(occupied=False, empty_since=now - timedelta(minutes=minutes))


@pytest.mark.parametrize(
    ("now", "start", "end", "expected"),
    [
        (time(23, 0), time(22, 30), time(8, 0), True),
        (time(7, 59), time(22, 30), time(8, 0), True),
        (time(8, 0), time(22, 30), time(8, 0), False),
        (time(12, 0), time(9, 0), time(17, 0), True),
        (time(17, 0), time(9, 0), time(17, 0), False),
        (time(12, 0), time(9, 0), time(9, 0), False),
    ],
)
def test_in_window(now, start, end, expected) -> None:
    assert in_window(now, start, end) is expected


def test_empty_room_gets_full_pass_first() -> None:
    now = at(10)
    p = plan(now, G, [(sensor_room(), empty_for(15, now))], READY)
    assert p.decision == Decision("living", CleanKind.FULL, forced=False, quiet=False)
    assert p.statuses["living"] is RoomStatus.READY


def test_room_must_stay_empty_long_enough() -> None:
    now = at(10)
    p = plan(now, G, [(sensor_room(), empty_for(5, now))], READY)
    assert p.decision is None
    assert p.statuses["living"] is RoomStatus.WAITING_OCCUPIED


def test_occupied_room_waits_before_deadline() -> None:
    p = plan(at(10), G, [(sensor_room(), RoomState(occupied=True))], READY)
    assert p.decision is None
    assert p.statuses["living"] is RoomStatus.WAITING_OCCUPIED


def test_occupied_room_is_forced_and_quiet_after_deadline() -> None:
    p = plan(at(19, 5), G, [(sensor_room(), RoomState(occupied=True))], READY)
    assert p.decision == Decision("living", CleanKind.FULL, forced=True, quiet=True)


def test_forced_but_empty_room_is_not_quiet() -> None:
    now = at(19, 5)
    p = plan(now, G, [(sensor_room(), empty_for(30, now))], READY)
    assert p.decision == Decision("living", CleanKind.FULL, forced=True, quiet=False)


def test_unavailable_sensor_counts_as_occupied() -> None:
    p = plan(at(10), G, [(sensor_room(), RoomState(occupied=None))], READY)
    assert p.statuses["living"] is RoomStatus.WAITING_OCCUPIED


def test_second_vacuum_waits_for_gap() -> None:
    now = at(12)
    st = empty_for(30, now)
    st.full_today, st.vacuum_today = 1, 1
    st.last_full = st.last_vacuum = at(9)
    p = plan(now, G, [(sensor_room(), st)], READY)
    assert p.decision is None
    assert p.statuses["living"] is RoomStatus.WAITING_GAP

    later = at(15, 1)
    st.empty_since = later - timedelta(minutes=30)
    p = plan(later, G, [(sensor_room(), st)], READY)
    assert p.decision == Decision("living", CleanKind.VACUUM, forced=False, quiet=False)


def test_done_when_all_targets_met() -> None:
    st = RoomState(occupied=False, full_today=1, vacuum_today=2)
    p = plan(at(16), G, [(sensor_room(), st)], READY)
    assert p.statuses["living"] is RoomStatus.DONE


def test_quiet_hours_block_even_forced_jobs() -> None:
    p = plan(at(23), G, [(sensor_room(), RoomState(occupied=True))], READY)
    assert p.decision is None
    assert p.statuses["living"] is RoomStatus.WAITING_QUIET_HOURS


def test_wake_gate() -> None:
    now = at(9)
    p = plan(now, G, [(sensor_room(), empty_for(60, now))], READY, awake=False)
    assert p.decision is None
    assert p.statuses["living"] is RoomStatus.WAITING_AWAKE


def test_proxy_room_is_free_only_while_proxy_active() -> None:
    study = RoomConfig("study", "study", proxy_sensors=("binary_sensor.kitchen",))
    p = plan(at(13), G, [(study, RoomState(proxy_active=False))], READY)
    assert p.statuses["study"] is RoomStatus.WAITING_OCCUPIED
    p = plan(at(13), G, [(study, RoomState(proxy_active=True))], READY)
    assert p.decision == Decision("study", CleanKind.FULL, forced=False, quiet=False)


def test_room_without_any_sensor_is_always_free() -> None:
    hall = RoomConfig("hall", "hall")
    p = plan(at(10), G, [(hall, RoomState())], READY)
    assert p.decision is not None and p.decision.room_id == "hall"


def test_priority_forced_then_full_then_longest_wait_then_order() -> None:
    now = at(19, 30)  # full deadline passed, vacuum deadline not yet
    vac_due = empty_for(60, now)
    vac_due.full_today, vac_due.vacuum_today = 1, 1
    vac_due.last_vacuum = at(9)
    rooms = [
        (sensor_room("a"), vac_due),  # vacuum, not forced
        (sensor_room("b"), RoomState(occupied=True)),  # full, forced
        (sensor_room("c"), empty_for(60, now)),  # full, forced, free
    ]
    p = plan(now, G, rooms, READY)
    assert p.decision is not None and p.decision.room_id == "b"

    now = at(11)
    old, new = empty_for(60, now), empty_for(60, now)
    old.last_full, new.last_full = at(0) - timedelta(days=2), at(0) - timedelta(days=1)
    p = plan(now, G, [(sensor_room("new"), new), (sensor_room("old"), old)], READY)
    assert p.decision is not None and p.decision.room_id == "old"


def test_robot_not_ready() -> None:
    now = at(10)
    rooms = [(sensor_room(), empty_for(30, now))]
    for robot in (
        RobotState(available=False, idle=True),
        RobotState(available=True, idle=False),
        RobotState(available=True, idle=True, battery=10),
    ):
        p = plan(now, G, rooms, robot)
        assert p.decision is None
        assert p.statuses["living"] is RoomStatus.WAITING_ROBOT


def test_active_room_and_disabled_room() -> None:
    now = at(10)
    off = empty_for(30, now)
    off.enabled = False
    rooms = [(sensor_room("a"), empty_for(30, now)), (sensor_room("b"), off)]
    p = plan(now, G, rooms, READY, active_room="a")
    assert p.decision is None
    assert p.statuses == {"a": RoomStatus.CLEANING, "b": RoomStatus.DISABLED}


def test_should_interrupt() -> None:
    cfg = sensor_room()
    normal = Decision("living", CleanKind.FULL, forced=False, quiet=False)
    forced = Decision("living", CleanKind.FULL, forced=True, quiet=False)
    assert should_interrupt(cfg, RoomState(occupied=True), normal)
    assert not should_interrupt(cfg, RoomState(occupied=False), normal)
    assert not should_interrupt(cfg, RoomState(occupied=True), forced)

    study = RoomConfig("study", "study", proxy_sensors=("binary_sensor.kitchen",))
    assert should_interrupt(study, RoomState(proxy_active=False), normal)
    assert not should_interrupt(study, RoomState(proxy_active=True), normal)
