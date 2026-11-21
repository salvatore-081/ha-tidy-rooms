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
    WaitReason,
    in_window,
    next_room,
    outlook,
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


# ---------------------------------------------------------------- outlook


def test_outlook_empty_room_starts_when_free() -> None:
    now = at(10)
    ol = outlook(now, G, sensor_room(), empty_for(4, now))
    assert ol.kind is CleanKind.FULL
    assert ol.earliest == at(10, 6)
    assert ol.reason is WaitReason.EMPTY
    assert ol.free_at == at(10, 6)
    assert ol.deadline == at(19)
    assert (ol.full_left, ol.vacuum_left) == (1, 2)


def test_outlook_free_room_starts_now() -> None:
    now = at(10)
    ol = outlook(now, G, sensor_room(), empty_for(30, now))
    assert ol.earliest == now
    assert ol.reason is None


def test_outlook_occupied_room_waits_for_deadline() -> None:
    now = at(10)
    ol = outlook(now, G, sensor_room(), RoomState(occupied=True))
    assert ol.earliest == at(19)
    assert ol.reason is WaitReason.OCCUPIED
    assert ol.free_at is None


def test_outlook_occupied_without_deadline_is_unknown() -> None:
    now = at(10)
    ol = outlook(now, G, sensor_room(full_deadline=None), RoomState(occupied=True))
    assert ol.earliest is None
    assert ol.reason is WaitReason.OCCUPIED


def test_outlook_occupied_past_deadline_starts_now() -> None:
    now = at(19, 30)
    ol = outlook(now, G, sensor_room(), RoomState(occupied=True))
    assert ol.earliest == now
    assert ol.reason is None


def test_outlook_vacuum_waits_for_gap() -> None:
    now = at(12)
    st = empty_for(60, now)
    st.full_today = st.vacuum_today = 1
    st.last_full = st.last_vacuum = at(10)
    ol = outlook(now, G, sensor_room(), st)
    assert ol.kind is CleanKind.VACUUM
    assert ol.earliest == at(16)
    assert ol.reason is WaitReason.GAP
    assert ol.deadline == at(21, 30)


def test_outlook_quiet_hours_until_morning() -> None:
    now = at(6)
    ol = outlook(now, G, sensor_room(), empty_for(60, now))
    assert ol.earliest == at(8)
    assert ol.reason is WaitReason.QUIET_HOURS


def test_outlook_gap_ending_in_quiet_hours_is_not_today() -> None:
    now = at(20)
    st = empty_for(60, now)
    st.full_today = st.vacuum_today = 1
    st.last_vacuum = at(17)
    ol = outlook(now, G, sensor_room(), st)
    assert ol.earliest is None
    assert ol.reason is WaitReason.NOT_TODAY


def test_outlook_done_room() -> None:
    now = at(20)
    st = RoomState(full_today=1, vacuum_today=2)
    ol = outlook(now, G, sensor_room(), st)
    assert ol.kind is None and ol.earliest is None
    assert (ol.full_left, ol.vacuum_left) == (0, 0)


def test_outlook_not_awake() -> None:
    now = at(9)
    ol = outlook(now, G, sensor_room(), empty_for(60, now), awake=False)
    assert ol.earliest == now
    assert ol.reason is WaitReason.AWAKE


def test_outlook_proxy_room() -> None:
    now = at(10)
    cfg = RoomConfig("study", "study", proxy_sensors=("binary_sensor.k",))
    assert outlook(now, G, cfg, RoomState(proxy_active=True)).earliest == now
    ol = outlook(now, G, cfg, RoomState(proxy_active=False))
    assert ol.earliest == at(19)
    assert ol.reason is WaitReason.OCCUPIED


def test_outlook_room_without_sensors() -> None:
    now = at(10)
    assert outlook(now, G, RoomConfig("hall", "hall"), RoomState()).earliest == now


def test_next_room_prefers_earliest_then_priority() -> None:
    now = at(10)
    a = outlook(now, G, sensor_room("a"), empty_for(30, now))
    b = outlook(now, G, sensor_room("b"), empty_for(8, now))
    assert next_room({"a": a, "b": b}, ["b", "a"]) == "a"
    c = outlook(now, G, sensor_room("c"), empty_for(30, now))
    assert next_room({"a": a, "c": c}, ["c", "a"]) == "c"
    assert next_room({}, []) is None


def test_outlook_utc_timestamps_near_midnight() -> None:
    """Sensor timestamps in UTC are compared in local time."""
    from zoneinfo import ZoneInfo

    rome = ZoneInfo("Europe/Rome")
    now = datetime(2026, 1, 12, 0, 30, tzinfo=rome)  # 23:30 UTC the day before
    g = GlobalConfig(quiet_start=None, quiet_end=None)
    st = RoomState(
        occupied=False,
        empty_since=(now - timedelta(minutes=5)).astimezone(ZoneInfo("UTC")),
    )
    ol = outlook(now, g, sensor_room(), st)
    assert ol.earliest == now + timedelta(minutes=5)
    assert ol.earliest.tzinfo == rome
