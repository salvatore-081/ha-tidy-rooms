"""The planner of Tidy Rooms 0.3.0, frozen: test_planner.py checks that a
converted room gets the same decisions.

Pure planning logic for Tidy Rooms.

Nothing in this module talks to Home Assistant: it receives a snapshot of the
house (rooms, their occupancy, what has been cleaned today, the robot) and
returns what the robot should do next and why each room is waiting. This keeps
the rules easy to test and to reason about.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from enum import StrEnum


class CleanKind(StrEnum):
    """Kind of cleaning pass."""

    FULL = "full"  # vacuum, then mop
    VACUUM = "vacuum"  # vacuum only


class RoomStatus(StrEnum):
    """Why a room is (or is not) going to be cleaned."""

    DISABLED = "disabled"
    DONE = "done"  # all daily targets met
    WAITING_GAP = "waiting_gap"  # next pass due later (minimum gap)
    WAITING_OCCUPIED = "waiting_occupied"  # due, but someone is there
    WAITING_QUIET_HOURS = "waiting_quiet_hours"
    WAITING_AWAKE = "waiting_awake"  # due, household not up yet
    WAITING_ROBOT = "waiting_robot"  # due and free, robot busy or unavailable
    READY = "ready"  # due and free: will be cleaned
    CLEANING = "cleaning"


@dataclass(frozen=True, slots=True)
class RoomConfig:
    """Static configuration of a room."""

    room_id: str
    name: str
    occupancy_sensors: tuple[str, ...] = ()
    # For rooms without their own sensor: the room counts as free while any of
    # these sensors (in other rooms) reports someone there.
    proxy_sensors: tuple[str, ...] = ()
    empty_minutes: int = 10
    full_per_day: int = 1
    vacuum_per_day: int = 2  # a full pass counts as a vacuum pass too
    min_gap: timedelta = timedelta(hours=6)
    full_deadline: time | None = time(19, 0)
    vacuum_deadline: time | None = time(21, 30)


@dataclass(slots=True)
class RoomState:
    """Live state of a room."""

    enabled: bool = True
    # None when the room has no sensors or all of them are unavailable.
    occupied: bool | None = None
    # When the room became empty (all sensors off); None if occupied/unknown.
    empty_since: datetime | None = None
    proxy_active: bool = False
    full_today: int = 0
    vacuum_today: int = 0
    last_full: datetime | None = None
    last_vacuum: datetime | None = None


@dataclass(frozen=True, slots=True)
class GlobalConfig:
    """Settings shared by all rooms."""

    quiet_start: time | None = time(22, 30)
    quiet_end: time | None = time(8, 0)
    min_battery: int = 30


@dataclass(frozen=True, slots=True)
class RobotState:
    """What the planner needs to know about the robot."""

    available: bool
    idle: bool  # docked (or idle) and ready to take a job
    battery: int | None = None


@dataclass(frozen=True, slots=True)
class Decision:
    """A job for the robot."""

    room_id: str
    kind: CleanKind
    forced: bool  # deadline passed: clean even if occupied
    quiet: bool  # use the quiet fan speed


@dataclass(slots=True)
class Plan:
    """Planner output."""

    decision: Decision | None
    statuses: dict[str, RoomStatus] = field(default_factory=dict)


def in_window(now: time, start: time, end: time) -> bool:
    """Return True if `now` is in [start, end), handling windows past midnight."""
    if start == end:
        return False
    if start < end:
        return start <= now < end
    return now >= start or now < end


def _past(now: datetime, deadline: time | None) -> bool:
    return deadline is not None and now.time() >= deadline


def due_kind(cfg: RoomConfig, st: RoomState, now: datetime) -> CleanKind | None:
    """Return the pass the room needs now, ignoring occupancy."""
    if st.full_today < cfg.full_per_day:
        return CleanKind.FULL
    if st.vacuum_today < cfg.vacuum_per_day:  # noqa: SIM102 (frozen copy)
        if st.last_vacuum is None or now - st.last_vacuum >= cfg.min_gap:
            return CleanKind.VACUUM
    return None


def is_free(cfg: RoomConfig, st: RoomState, now: datetime) -> bool:
    """Return True if nobody is in the room (as far as we can tell)."""
    if cfg.occupancy_sensors:
        if st.occupied is not False or st.empty_since is None:
            return False
        return now - st.empty_since >= timedelta(minutes=cfg.empty_minutes)
    if cfg.proxy_sensors:
        return st.proxy_active
    return True


def plan(
    now: datetime,
    gcfg: GlobalConfig,
    rooms: list[tuple[RoomConfig, RoomState]],
    robot: RobotState,
    *,
    awake: bool = True,
    active_room: str | None = None,
) -> Plan:
    """Decide the next job and the status of every room.

    `rooms` is in the user's preferred order, used as the last tie-breaker.
    `awake` is False while the household is considered asleep (wake gate).
    `active_room` is the room being cleaned now, if any.
    """
    result = Plan(decision=None)
    quiet_hours = (
        gcfg.quiet_start is not None
        and gcfg.quiet_end is not None
        and in_window(now.time(), gcfg.quiet_start, gcfg.quiet_end)
    )
    robot_ready = (
        robot.available
        and robot.idle
        and active_room is None
        and (robot.battery is None or robot.battery >= gcfg.min_battery)
    )

    candidates: list[tuple[tuple, Decision]] = []
    for index, (cfg, st) in enumerate(rooms):
        if cfg.room_id == active_room:
            result.statuses[cfg.room_id] = RoomStatus.CLEANING
            continue
        if not st.enabled:
            result.statuses[cfg.room_id] = RoomStatus.DISABLED
            continue
        kind = due_kind(cfg, st, now)
        if kind is None:
            done = (
                st.full_today >= cfg.full_per_day
                and st.vacuum_today >= cfg.vacuum_per_day
            )
            result.statuses[cfg.room_id] = (
                RoomStatus.DONE if done else RoomStatus.WAITING_GAP
            )
            continue
        if quiet_hours:
            result.statuses[cfg.room_id] = RoomStatus.WAITING_QUIET_HOURS
            continue
        if not awake:
            result.statuses[cfg.room_id] = RoomStatus.WAITING_AWAKE
            continue

        deadline = cfg.full_deadline if kind is CleanKind.FULL else cfg.vacuum_deadline
        forced = _past(now, deadline)
        free = is_free(cfg, st, now)
        if not free and not forced:
            result.statuses[cfg.room_id] = RoomStatus.WAITING_OCCUPIED
            continue

        result.statuses[cfg.room_id] = (
            RoomStatus.READY if robot_ready else RoomStatus.WAITING_ROBOT
        )
        last = st.last_full if kind is CleanKind.FULL else st.last_vacuum
        # Forced jobs first, then full passes, then the longest wait, then order.
        key = (
            0 if forced else 1,
            0 if kind is CleanKind.FULL else 1,
            last.timestamp() if last else float("-inf"),
            index,
        )
        candidates.append(
            (key, Decision(cfg.room_id, kind, forced=forced, quiet=forced and not free))
        )

    if robot_ready and candidates:
        candidates.sort(key=lambda c: c[0])
        result.decision = candidates[0][1]
    return result


def should_interrupt(cfg: RoomConfig, st: RoomState, decision: Decision) -> bool:
    """Return True if a running job must stop because someone came in.

    Forced jobs never stop: they switch to the quiet fan speed instead.
    """
    if decision.forced:
        return False
    if cfg.occupancy_sensors:
        return st.occupied is True
    if cfg.proxy_sensors:
        return not st.proxy_active
    return False


class WaitReason(StrEnum):
    """What the next pass of a room is waiting for."""

    GAP = "gap"  # minimum gap since the last pass
    QUIET_HOURS = "quiet_hours"
    AWAKE = "awake"  # wake-up check, time unknown
    EMPTY = "empty"  # room empty, not for long enough yet
    OCCUPIED = "occupied"  # someone is there: no time known until the deadline
    NOT_TODAY = "not_today"  # cannot start before midnight


@dataclass(frozen=True, slots=True)
class RoomOutlook:
    """When the next pass of a room can start, as far as we can tell now.

    The presence sensors can change at any time: `earliest` assumes the room
    stays as it is now (empty rooms stay empty, occupied rooms stay occupied
    until their deadline).
    """

    kind: CleanKind | None  # next pass still due today
    earliest: datetime | None  # None: done, unknown, or not today
    reason: WaitReason | None  # what `earliest` waits for (None: can start now)
    free_at: datetime | None  # when the room counts as empty, if it stays so
    deadline: datetime | None  # when the pass is forced
    full_left: int
    vacuum_left: int


def _at(now: datetime, t: time) -> datetime:
    return now.replace(hour=t.hour, minute=t.minute, second=t.second, microsecond=0)


def _after_quiet(moment: datetime, gcfg: GlobalConfig) -> datetime:
    """Move `moment` to the end of quiet hours if it falls inside them."""
    if (
        gcfg.quiet_start is None
        or gcfg.quiet_end is None
        or not in_window(moment.time(), gcfg.quiet_start, gcfg.quiet_end)
    ):
        return moment
    end = _at(moment, gcfg.quiet_end)
    return end if end > moment else end + timedelta(days=1)


def outlook(
    now: datetime,
    gcfg: GlobalConfig,
    cfg: RoomConfig,
    st: RoomState,
    *,
    awake: bool = True,
) -> RoomOutlook:
    """Estimate when the next pass of a room can start."""
    full_left = max(cfg.full_per_day - st.full_today, 0)
    vacuum_left = max(cfg.vacuum_per_day - st.vacuum_today, 0)
    kind = CleanKind.FULL if full_left else CleanKind.VACUUM if vacuum_left else None
    if kind is None or not st.enabled:
        return RoomOutlook(kind, None, None, None, None, full_left, vacuum_left)

    def local(moment: datetime) -> datetime:
        # Sensor timestamps are UTC: compare times and dates in `now`'s zone.
        if moment.tzinfo is not None and now.tzinfo is not None:
            return moment.astimezone(now.tzinfo)
        return moment

    deadline_t = cfg.full_deadline if kind is CleanKind.FULL else cfg.vacuum_deadline
    deadline = _at(now, deadline_t) if deadline_t is not None else None

    # Time constraints: minimum gap (vacuum passes only), quiet hours.
    start, reason = now, None
    if kind is CleanKind.VACUUM and st.last_vacuum is not None:
        gap_end = local(st.last_vacuum) + cfg.min_gap
        if gap_end > start:
            start, reason = gap_end, WaitReason.GAP
    moved = _after_quiet(start, gcfg)
    if moved != start:
        start, reason = moved, WaitReason.QUIET_HOURS

    # Presence: the room must be empty long enough, unless the deadline passed.
    free_at: datetime | None = None
    occupied = False
    if cfg.occupancy_sensors:
        if st.occupied is False and st.empty_since is not None:
            free_at = local(st.empty_since) + timedelta(minutes=cfg.empty_minutes)
        else:
            occupied = True
    elif cfg.proxy_sensors and not st.proxy_active:
        occupied = True

    candidates: list[tuple[datetime, WaitReason | None]] = []
    if not occupied:
        if free_at is not None and free_at > start:
            candidates.append((free_at, WaitReason.EMPTY))
        else:
            candidates.append((start, reason))
    if deadline is not None:
        forced_at = max(start, deadline)
        candidates.append(
            (forced_at, reason if forced_at == start else WaitReason.OCCUPIED)
        )

    if not candidates:
        return RoomOutlook(
            kind, None, WaitReason.OCCUPIED, free_at, deadline, full_left, vacuum_left
        )
    earliest, reason = min(candidates, key=lambda c: c[0])
    if not awake and reason is None:
        reason = WaitReason.AWAKE
    if earliest.date() != now.date():
        return RoomOutlook(
            kind, None, WaitReason.NOT_TODAY, free_at, deadline, full_left, vacuum_left
        )
    return RoomOutlook(
        kind, earliest, reason, free_at, deadline, full_left, vacuum_left
    )


def next_room(
    outlooks: dict[str, RoomOutlook],
    order: list[str],
) -> str | None:
    """The room expected to be cleaned next: earliest start, then `plan()` priorities."""
    best: tuple | None = None
    best_id: str | None = None
    for index, room_id in enumerate(order):
        ol = outlooks.get(room_id)
        if ol is None or ol.earliest is None or ol.kind is None:
            continue
        forced = ol.deadline is not None and ol.earliest >= ol.deadline
        key = (
            ol.earliest,
            0 if forced else 1,
            0 if ol.kind is CleanKind.FULL else 1,
            index,
        )
        if best is None or key < best:
            best, best_id = key, room_id
    return best_id
