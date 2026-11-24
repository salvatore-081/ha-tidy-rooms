"""Tests for the pure planner of cleaning programs."""

from __future__ import annotations

import itertools
from datetime import datetime, time, timedelta

import pytest

from custom_components.tidy_rooms.legacy import (
    KIND_FULL,
    legacy_done,
    legacy_kind,
    legacy_program,
)
from custom_components.tidy_rooms.planner import (
    Decision,
    GlobalConfig,
    PassConfig,
    PassDone,
    PassStatus,
    RobotState,
    RoomConfig,
    RoomState,
    RoomStatus,
    WaitReason,
    manual_target,
    next_room,
    outlook,
    pass_from_data,
    pass_states,
    plan,
    should_interrupt,
)

from . import planner_0_3_0 as old

DAY = datetime(2026, 1, 12)  # a Monday
READY = RobotState(available=True, idle=True, battery=100)
G = GlobalConfig()
SENSOR = ("binary_sensor.x",)


def at(hour: int, minute: int = 0) -> datetime:
    return DAY.replace(hour=hour, minute=minute)


DEFAULT_ROOM = {
    "full_per_day": 1,
    "vacuum_per_day": 2,
    "min_gap_hours": 6,
    "full_deadline": "19:00:00",
    "vacuum_deadline": "21:30:00",
}
MODES = {"full_mode_option": "mop_after_vacuum", "vacuum_mode_option": "vacuum"}


def legacy_room(room_id: str = "living", sensors=SENSOR, **room) -> RoomConfig:
    """The program a 0.3.0 room is migrated to (passes full-1, vacuum-1, …)."""
    data = {**DEFAULT_ROOM, **room}
    passes = legacy_program(data, MODES)
    return RoomConfig(
        room_id,
        room_id,
        occupancy_sensors=sensors,
        passes=tuple(pass_from_data(p) for p in passes),
    )


def room(*passes: PassConfig, room_id: str = "living", sensors=SENSOR) -> RoomConfig:
    return RoomConfig(room_id, room_id, occupancy_sensors=sensors, passes=passes)


def empty_for(minutes: int, now: datetime, **kw) -> RoomState:
    return RoomState(occupied=False, empty_since=now - timedelta(minutes=minutes), **kw)


def done(*pass_ids: str, at_: datetime | None = None, manual=False) -> list[PassDone]:
    return [PassDone(p, at_, manual=manual) for p in pass_ids]


# ------------------------------------------------------------ the program


def test_pass_from_data() -> None:
    p = pass_from_data(
        {
            "id": "a",
            "work_mode": "vacuum",
            "fan_speed": "max",
            "start": "09:00:00",
            "end": "12:00:00",
            "forced": False,
            "gap_hours": 1.5,
            "days": ["sat", "sun"],
        }
    )
    assert p == PassConfig(
        "a",
        "vacuum",
        "max",
        time(9),
        time(12),
        False,
        timedelta(hours=1, minutes=30),
        frozenset({5, 6}),
    )
    bare = pass_from_data({"id": "b"})
    assert bare == PassConfig("b")
    assert bare.forced and not bare.is_forced  # no deadline: never forced


def test_legacy_program_default_room() -> None:
    passes = legacy_program(DEFAULT_ROOM, MODES)
    assert passes == [
        {
            "id": "full-1",
            "forced": True,
            "work_mode": "mop_after_vacuum",
            "end": "19:00:00",
        },
        {
            "id": "vacuum-1",
            "forced": True,
            "work_mode": "vacuum",
            "end": "21:30:00",
            "gap_hours": 6.0,
        },
    ]
    assert legacy_kind("full-1") == KIND_FULL
    assert legacy_kind("vacuum-12") == "vacuum"
    assert legacy_kind("3f9a01bc") is None
    assert legacy_kind(None) is None


@pytest.mark.parametrize(
    ("room_data", "options", "expected"),
    [
        # No full pass: vacuum passes only, all with the gap.
        (
            {"full_per_day": 0, "vacuum_per_day": 2, "min_gap_hours": 4},
            {},
            [
                {"id": "vacuum-1", "forced": True, "gap_hours": 4.0},
                {"id": "vacuum-2", "forced": True, "gap_hours": 4.0},
            ],
        ),
        # As many full passes as vacuum passes: no vacuum-only pass.
        (
            {"full_per_day": 2, "vacuum_per_day": 2, "min_gap_hours": 6},
            {},
            [{"id": "full-1", "forced": True}, {"id": "full-2", "forced": True}],
        ),
        # Room modes and fan speed win over the global ones; no deadlines.
        (
            {
                "full_per_day": 1,
                "vacuum_per_day": 1,
                "full_mode": "vacuum_and_mop",
                "fan_speed": "max",
            },
            MODES,
            [
                {
                    "id": "full-1",
                    "forced": True,
                    "work_mode": "vacuum_and_mop",
                    "fan_speed": "max",
                }
            ],
        ),
        ({"full_per_day": 0, "vacuum_per_day": 0}, MODES, []),
    ],
)
def test_legacy_program_cases(room_data, options, expected) -> None:
    assert legacy_program(room_data, options) == expected


def test_legacy_done_converts_counts() -> None:
    passes = [
        p["id"] for p in legacy_program({**DEFAULT_ROOM, "vacuum_per_day": 3}, MODES)
    ]
    assert legacy_done(passes, 0, 0, None) == []
    assert legacy_done(passes, 1, 1, at(9)) == [PassDone("full-1", at(9), manual=True)]
    assert legacy_done(passes, 1, 2, at(15)) == [
        PassDone("full-1", None, manual=True),
        PassDone("vacuum-1", at(15), manual=True),
    ]
    # A vacuum pass done without the full one (old "clean now" button): the
    # full pass stays due, as in 0.3.0.
    assert legacy_done(passes, 0, 1, at(9)) == [
        PassDone("vacuum-1", at(9), manual=True)
    ]
    # More than planned: capped.
    assert len(legacy_done(passes, 3, 9, at(9))) == 3


# ----------------------------------------------------------- pass states


def test_pass_states_skips_closed_windows_unless_forced() -> None:
    cfg = room(
        PassConfig("a", end=time(12), forced=False),
        PassConfig("b", end=time(12)),
        PassConfig("c"),
    )
    assert pass_states(cfg, RoomState(), at(11)) == [PassStatus.PENDING] * 3
    assert pass_states(cfg, RoomState(), at(12)) == [
        PassStatus.SKIPPED,
        PassStatus.PENDING,  # forced: still due after the deadline
        PassStatus.PENDING,
    ]


def test_pass_states_gap_past_the_deadline_skips() -> None:
    cfg = room(PassConfig("a"), PassConfig("b", end=time(20), gap=timedelta(hours=6)))
    st = RoomState(done_today=done("a", at_=at(13)), last_clean=at(13))
    assert pass_states(cfg, st, at(13, 30))[1] is PassStatus.PENDING
    st = RoomState(done_today=done("a", at_=at(15)), last_clean=at(15))
    assert pass_states(cfg, st, at(15, 30))[1] is PassStatus.SKIPPED


def test_pass_states_later_pass_done_skips_earlier() -> None:
    cfg = room(PassConfig("a"), PassConfig("b"), PassConfig("c"))
    st = RoomState(done_today=done("b", at_=at(10)))
    assert pass_states(cfg, st, at(11)) == [
        PassStatus.SKIPPED,
        PassStatus.DONE,
        PassStatus.PENDING,
    ]
    # A manual cleaning counted on "b" leaves "a" pending.
    st = RoomState(done_today=done("b", at_=at(10), manual=True))
    assert pass_states(cfg, st, at(11))[0] is PassStatus.PENDING


def test_pass_states_active_pass() -> None:
    cfg = room(PassConfig("a"), PassConfig("b", end=time(12), forced=False))
    # The running pass is never skipped, even past its deadline.
    states = pass_states(
        RoomConfig("r", "r", passes=cfg.passes),
        RoomState(),
        at(12, 30),
        active_pass_id="b",
    )
    assert states == [PassStatus.SKIPPED, PassStatus.ACTIVE]
    states = pass_states(
        cfg, RoomState(), at(10), active_pass_id="b", active_manual=True
    )
    assert states == [PassStatus.PENDING, PassStatus.ACTIVE]


def test_pass_states_days_and_unknown_ids() -> None:
    cfg = room(PassConfig("a", days=frozenset({5, 6})), PassConfig("b"))
    st = RoomState(done_today=done("gone", at_=at(9)))  # pass removed from the program
    assert pass_states(cfg, st, at(10)) == [PassStatus.NOT_TODAY, PassStatus.PENDING]


# ------------------------------------------------------------------ plan


def test_empty_room_gets_first_pass() -> None:
    now = at(10)
    p = plan(now, G, [(legacy_room(), empty_for(15, now))], READY)
    assert p.decision == Decision(
        "living", "full-1", "mop_after_vacuum", None, forced=False, quiet=False
    )
    assert p.statuses["living"] is RoomStatus.READY


def test_room_must_stay_empty_long_enough() -> None:
    now = at(10)
    p = plan(now, G, [(legacy_room(), empty_for(5, now))], READY)
    assert p.decision is None
    assert p.statuses["living"] is RoomStatus.WAITING_OCCUPIED


def test_occupied_room_is_forced_and_quiet_after_deadline() -> None:
    p = plan(at(19, 5), G, [(legacy_room(), RoomState(occupied=True))], READY)
    assert p.decision is not None
    assert (p.decision.pass_id, p.decision.forced, p.decision.quiet) == (
        "full-1",
        True,
        True,
    )


def test_forced_but_empty_room_is_not_quiet() -> None:
    now = at(19, 5)
    p = plan(now, G, [(legacy_room(), empty_for(30, now))], READY)
    assert p.decision is not None and p.decision.forced and not p.decision.quiet


def test_window_start_and_gap() -> None:
    cfg = room(
        PassConfig("a", start=time(9), end=time(12)),
        PassConfig("b", "vacuum", "max", start=time(17), gap=timedelta(hours=2)),
    )
    early = GlobalConfig(quiet_end=time(7))
    p = plan(at(8, 30), early, [(cfg, empty_for(60, at(8, 30)))], READY)
    assert p.statuses["living"] is RoomStatus.WAITING_WINDOW

    st = empty_for(60, at(16), done_today=done("a", at_=at(16)), last_clean=at(16))
    p = plan(at(16, 30), G, [(cfg, st)], READY)
    assert p.statuses["living"] is RoomStatus.WAITING_WINDOW
    st.last_clean = at(16, 30)
    p = plan(at(17, 30), G, [(cfg, st)], READY)
    assert p.statuses["living"] is RoomStatus.WAITING_GAP
    p = plan(at(18, 30), G, [(cfg, st)], READY)
    assert p.decision == Decision(
        "living", "b", "vacuum", "max", forced=False, quiet=False
    )


def test_pass_without_deadline_is_overtaken_at_a_forced_deadline() -> None:
    cfg = room(PassConfig("a"), PassConfig("b", end=time(18)))
    occupied = RoomState(occupied=True)
    p = plan(at(17), G, [(cfg, occupied)], READY)
    assert p.statuses["living"] is RoomStatus.WAITING_OCCUPIED
    p = plan(at(18), G, [(cfg, occupied)], READY)
    assert p.decision is not None and p.decision.pass_id == "b" and p.decision.forced
    # Once "b" started, "a" counts as skipped.
    states = pass_states(cfg, occupied, at(18), active_pass_id="b")
    assert states == [PassStatus.SKIPPED, PassStatus.ACTIVE]


def test_done_when_nothing_is_pending() -> None:
    cfg = legacy_room()
    st = RoomState(occupied=False, done_today=done("full-1", "vacuum-1", at_=at(15)))
    assert plan(at(16), G, [(cfg, st)], READY).statuses["living"] is RoomStatus.DONE
    # Empty program, or no pass today.
    assert (
        plan(at(16), G, [(room(), RoomState())], READY).statuses["living"]
        is RoomStatus.DONE
    )
    weekend = room(PassConfig("a", days=frozenset({5, 6})))
    assert (
        plan(at(16), G, [(weekend, RoomState())], READY).statuses["living"]
        is RoomStatus.DONE
    )


def test_quiet_hours_wake_gate_robot_and_disabled() -> None:
    now = at(10)
    cfg = legacy_room()
    assert (
        plan(at(23), G, [(cfg, RoomState(occupied=True))], READY).statuses["living"]
        is RoomStatus.WAITING_QUIET_HOURS
    )
    p = plan(now, G, [(cfg, empty_for(60, now))], READY, awake=False)
    assert p.decision is None and p.statuses["living"] is RoomStatus.WAITING_AWAKE
    p = plan(
        now, G, [(cfg, empty_for(60, now))], RobotState(available=True, idle=False)
    )
    assert p.decision is None and p.statuses["living"] is RoomStatus.WAITING_ROBOT
    off = empty_for(30, now)
    off.enabled = False
    p = plan(
        now,
        G,
        [(cfg, empty_for(30, now)), (legacy_room("b"), off)],
        READY,
        active_room="living",
    )
    assert p.decision is None
    assert p.statuses == {"living": RoomStatus.CLEANING, "b": RoomStatus.DISABLED}


def test_proxy_room_and_room_without_sensors() -> None:
    study = legacy_room("study", sensors=())
    study = RoomConfig(
        "study", "study", proxy_sensors=("binary_sensor.k",), passes=study.passes
    )
    p = plan(at(13), G, [(study, RoomState(proxy_active=False))], READY)
    assert p.statuses["study"] is RoomStatus.WAITING_OCCUPIED
    p = plan(at(13), G, [(study, RoomState(proxy_active=True))], READY)
    assert p.decision is not None and p.decision.room_id == "study"
    hall = legacy_room("hall", sensors=())
    assert plan(at(10), G, [(hall, RoomState())], READY).decision is not None


def test_priority_forced_then_deadline_then_longest_wait_then_order() -> None:
    now = at(11)
    noon = room(PassConfig("a", end=time(12)), room_id="noon")
    evening = room(PassConfig("a", end=time(19)), room_id="evening")
    late = room(PassConfig("a", end=time(10)), room_id="late")  # forced now
    rooms = [(evening, empty_for(60, now)), (noon, empty_for(60, now))]
    assert plan(now, G, rooms, READY).decision.room_id == "noon"  # type: ignore[union-attr]
    rooms.append((late, RoomState(occupied=True)))
    assert plan(now, G, rooms, READY).decision.room_id == "late"  # type: ignore[union-attr]

    a, b = legacy_room("a"), legacy_room("b")
    old_st = empty_for(60, now, last_clean=at(0) - timedelta(days=2))
    new_st = empty_for(60, now, last_clean=at(0) - timedelta(days=1))
    assert plan(now, G, [(b, new_st), (a, old_st)], READY).decision.room_id == "a"  # type: ignore[union-attr]
    same = [(b, empty_for(60, now)), (a, empty_for(60, now))]
    assert plan(now, G, same, READY).decision.room_id == "b"  # type: ignore[union-attr]


def test_should_interrupt() -> None:
    cfg = legacy_room()
    normal = Decision("living", "full-1", None, None, forced=False, quiet=False)
    forced = Decision("living", "full-1", None, None, forced=True, quiet=False)
    assert should_interrupt(cfg, RoomState(occupied=True), normal)
    assert not should_interrupt(cfg, RoomState(occupied=False), normal)
    assert not should_interrupt(cfg, RoomState(occupied=True), forced)


def test_manual_target() -> None:
    cfg = room(
        PassConfig("a", "mop_after_vacuum", end=time(12), forced=False),
        PassConfig("b", "vacuum"),
        PassConfig("c", "vacuum"),
    )
    st = RoomState()
    assert manual_target(cfg, st, at(10), "vacuum").pass_id == "b"  # type: ignore[union-attr]
    # A skipped pass with the same mode counts.
    assert manual_target(cfg, st, at(13), "mop_after_vacuum").pass_id == "a"  # type: ignore[union-attr]
    assert manual_target(cfg, st, at(10), "mop") is None
    st.done_today = done("b", "c", at_=at(11))
    assert manual_target(cfg, st, at(13), "vacuum") is None


# --------------------------------------------------------------- outlook


def test_outlook_empty_room_starts_when_free() -> None:
    now = at(10)
    ol = outlook(now, G, legacy_room(), empty_for(4, now))
    assert (ol.pass_id, ol.position, ol.total, ol.done, ol.skipped) == (
        "full-1",
        1,
        2,
        0,
        0,
    )
    assert ol.work_mode == "mop_after_vacuum"
    assert ol.earliest == at(10, 6) and ol.reason is WaitReason.EMPTY
    assert ol.free_at == at(10, 6)
    assert ol.deadline == at(19) and ol.forced


def test_outlook_occupied_room_waits_for_deadline() -> None:
    now = at(10)
    ol = outlook(now, G, legacy_room(), RoomState(occupied=True))
    assert ol.earliest == at(19) and ol.reason is WaitReason.OCCUPIED
    no_deadline = room(PassConfig("a"))
    ol = outlook(now, G, no_deadline, RoomState(occupied=True))
    assert ol.earliest is None and ol.reason is WaitReason.OCCUPIED
    not_forced = room(PassConfig("a", end=time(12), forced=False))
    ol = outlook(now, G, not_forced, RoomState(occupied=True))
    assert ol.earliest is None and ol.reason is WaitReason.OCCUPIED


def test_outlook_window_gap_and_quiet_hours() -> None:
    now = at(12)
    cfg = room(PassConfig("a", start=time(14)))
    ol = outlook(now, G, cfg, empty_for(60, now))
    assert ol.earliest == at(14) and ol.reason is WaitReason.WINDOW

    st = empty_for(60, now, done_today=done("full-1", at_=at(10)), last_clean=at(10))
    ol = outlook(now, G, legacy_room(), st)
    assert (ol.pass_id, ol.position, ol.done) == ("vacuum-1", 2, 1)
    assert ol.earliest == at(16) and ol.reason is WaitReason.GAP

    ol = outlook(at(6), G, legacy_room(), empty_for(60, at(6)))
    assert ol.earliest == at(8) and ol.reason is WaitReason.QUIET_HOURS


def test_outlook_not_forced_pass_that_cannot_fit() -> None:
    now = at(11)
    cfg = room(PassConfig("a", start=time(11, 30), end=time(12), forced=False))
    ol = outlook(now, G, cfg, empty_for(1, now))
    assert ol.earliest == at(11, 30)
    ol = outlook(
        now,
        GlobalConfig(quiet_start=time(11), quiet_end=time(13)),
        cfg,
        empty_for(60, now),
    )
    assert ol.earliest is None and ol.reason is WaitReason.NOT_TODAY


def test_outlook_done_and_not_awake() -> None:
    st = RoomState(done_today=done("full-1", "vacuum-1", at_=at(15)))
    ol = outlook(at(20), G, legacy_room(), st)
    assert ol.pass_id is None and ol.earliest is None and (ol.done, ol.total) == (2, 2)
    ol = outlook(at(9), G, legacy_room(), empty_for(60, at(9)), awake=False)
    assert ol.earliest == at(9) and ol.reason is WaitReason.AWAKE


def test_outlook_utc_timestamps_near_midnight() -> None:
    from zoneinfo import ZoneInfo

    rome = ZoneInfo("Europe/Rome")
    now = datetime(2026, 1, 12, 0, 30, tzinfo=rome)
    g = GlobalConfig(quiet_start=None, quiet_end=None)
    st = RoomState(
        occupied=False,
        empty_since=(now - timedelta(minutes=5)).astimezone(ZoneInfo("UTC")),
    )
    ol = outlook(now, g, legacy_room(), st)
    assert ol.earliest == now + timedelta(minutes=5)


def test_next_room_prefers_earliest_then_priority() -> None:
    now = at(10)
    a = outlook(now, G, legacy_room("a"), empty_for(30, now))
    b = outlook(now, G, legacy_room("b"), empty_for(8, now))
    assert next_room({"a": a, "b": b}, ["b", "a"]) == "a"
    c = outlook(now, G, legacy_room("c"), empty_for(30, now))
    assert next_room({"a": a, "c": c}, ["c", "a"]) == "c"
    assert next_room({}, []) is None


# ----------------------------------------- same decisions as Tidy Rooms 0.3.0


def _old_room(room_id: str, data: dict) -> old.RoomConfig:
    return old.RoomConfig(
        room_id,
        room_id,
        occupancy_sensors=SENSOR,
        full_per_day=data["full_per_day"],
        vacuum_per_day=data["vacuum_per_day"],
        min_gap=timedelta(hours=data["min_gap_hours"]),
        full_deadline=time.fromisoformat(data["full_deadline"]),
        vacuum_deadline=time.fromisoformat(data["vacuum_deadline"]),
    )


ROOMS = {
    "a": DEFAULT_ROOM,
    "b": {**DEFAULT_ROOM, "full_per_day": 0, "vacuum_per_day": 2, "min_gap_hours": 3},
    "c": {**DEFAULT_ROOM, "vacuum_per_day": 3, "min_gap_hours": 2},
}
# (full_today, vacuum_today, last pass)
PROGRESS = [
    (0, 0, None),
    (1, 1, (9, 0)),
    (1, 1, (14, 0)),
    (1, 2, (16, 0)),
    (0, 1, (8, 30)),
]


def _gap_past_deadline(data: dict, progress, now: datetime) -> bool:
    """The case that changed on purpose: the gap ends after the deadline."""
    full, vac, last = progress
    if last is None or vac >= data["vacuum_per_day"] or full < data["full_per_day"]:
        return False
    gap_end = at(*last) + timedelta(hours=data["min_gap_hours"])
    return gap_end > at(*map(int, data["vacuum_deadline"].split(":")[:2]))


def _scenarios():
    times = [at(h, m) for h in (7, 9, 12, 15, 17, 19, 20, 21, 22) for m in (0, 45)]
    occupancy = ["free", "occupied", "recent"]
    for now, (rid, data), progress, occ in itertools.product(
        times, ROOMS.items(), PROGRESS, occupancy
    ):
        full, _, last = progress
        if full > data["full_per_day"] or (last is not None and at(*last) > now):
            continue  # not a possible 0.3.0 state
        if _gap_past_deadline(data, progress, now):
            continue  # changed on purpose: test_pass_states_gap_past_the_deadline_skips
        yield now, rid, data, progress, occ


@pytest.mark.parametrize(("now", "rid", "data", "progress", "occ"), list(_scenarios()))
def test_same_decisions_as_0_3_0(now, rid, data, progress, occ) -> None:
    full, vac, last = progress
    last_at = at(*last) if last else None
    occupied = occ == "occupied"
    since = None if occupied else now - timedelta(minutes=60 if occ == "free" else 3)

    old_st = old.RoomState(
        occupied=occupied,
        empty_since=since,
        full_today=full,
        vacuum_today=vac,
        last_full=last_at if full else None,
        last_vacuum=last_at,
    )
    old_plan = old.plan(now, G_OLD, [(_old_room(rid, data), old_st)], OLD_READY)

    passes = legacy_program(data, MODES)
    cfg = RoomConfig(
        rid,
        rid,
        occupancy_sensors=SENSOR,
        passes=tuple(pass_from_data(p) for p in passes),
    )
    new_st = RoomState(
        occupied=occupied,
        empty_since=since,
        done_today=legacy_done([p["id"] for p in passes], full, vac, last_at),
        last_clean=last_at,
    )
    new_plan = plan(now, G, [(cfg, new_st)], READY)

    assert new_plan.statuses[rid].value == old_plan.statuses[rid].value
    if old_plan.decision is None:
        assert new_plan.decision is None
        return
    d = new_plan.decision
    assert d is not None
    assert legacy_kind(d.pass_id) == old_plan.decision.kind.value
    assert (d.forced, d.quiet) == (old_plan.decision.forced, old_plan.decision.quiet)


G_OLD = old.GlobalConfig()
OLD_READY = old.RobotState(available=True, idle=True, battery=100)


def test_manual_target_any_mode() -> None:
    """Without a work mode entity, a manual cleaning counts as the next pass."""
    cfg = room(PassConfig("a", "mop_after_vacuum"), PassConfig("b", "vacuum"))
    target = manual_target(cfg, RoomState(), at(10), None, any_mode=True)
    assert target is not None and target.pass_id == "a"


def test_outlook_not_before_ignores_presence() -> None:
    """The end of the gap, even when the room is occupied until the deadline."""
    st = RoomState(
        occupied=True, done_today=done("full-1", at_=at(15)), last_clean=at(15)
    )
    ol = outlook(at(16), G, legacy_room(min_gap_hours=2), st)
    assert ol.earliest == at(21, 30) and ol.reason is WaitReason.OCCUPIED
    assert ol.not_before == at(17)
