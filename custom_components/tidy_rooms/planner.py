"""Pure planning logic for Tidy Rooms, based on a cleaning program per room.

Nothing in this module talks to Home Assistant: it receives a snapshot of the
house (rooms with their programs, their occupancy, what has been cleaned
today, the robot) and returns what the robot should do next and why each room
is waiting. This keeps the rules easy to test and to reason about.

A room's program is an ordered list of passes. The order matters: a pass
waits for the earlier ones while their window is open or still to come. A
pass whose window closes without a cleaning is skipped and does not block
the next ones; when a later pass starts, every earlier pass still pending is
skipped too.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from typing import Any

from .const import (
    CONF_DAYS,
    CONF_END,
    CONF_FAN_SPEED,
    CONF_FORCED,
    CONF_GAP_HOURS,
    CONF_PASS_ID,
    CONF_START,
    CONF_WORK_MODE,
    WEEKDAYS,
)


class RoomStatus(StrEnum):
    """Why a room is (or is not) going to be cleaned."""

    DISABLED = "disabled"
    DONE = "done"  # no pass left today (done, skipped or not today)
    WAITING_WINDOW = "waiting_window"  # next pass not before its start time
    WAITING_GAP = "waiting_gap"  # next pass due later (minimum gap)
    WAITING_OCCUPIED = "waiting_occupied"  # due, but someone is there
    WAITING_QUIET_HOURS = "waiting_quiet_hours"
    WAITING_AWAKE = "waiting_awake"  # due, household not up yet
    WAITING_ROBOT = "waiting_robot"  # due and free, robot busy or unavailable
    READY = "ready"  # due and free: will be cleaned
    CLEANING = "cleaning"


class PassStatus(StrEnum):
    """Where a pass of the program stands today."""

    NOT_TODAY = "not_today"  # its days do not include today
    DONE = "done"
    ACTIVE = "active"  # being cleaned now
    SKIPPED = "skipped"
    PENDING = "pending"


@dataclass(frozen=True, slots=True)
class PassConfig:
    """One pass of a room's program."""

    pass_id: str
    work_mode: str | None = None  # None: leave the robot's work mode as it is
    fan_speed: str | None = None  # None: the global normal fan speed
    start: time | None = None  # not before
    end: time | None = None  # deadline
    forced: bool = True  # cleaned at the deadline even if the room is occupied
    gap: timedelta | None = None  # since the last pass done in the room
    days: frozenset[int] | None = None  # weekdays (0 = Monday); None: every day

    def applies(self, day: date) -> bool:
        """Return True if the pass is planned on `day`."""
        return self.days is None or day.weekday() in self.days

    @property
    def is_forced(self) -> bool:
        """Forced at the deadline (a pass without deadline never is)."""
        return self.forced and self.end is not None


def _parse_time(value: Any) -> time | None:
    return time.fromisoformat(value) if value else None


def pass_from_data(data: dict[str, Any]) -> PassConfig:
    """A pass as saved in the room's subentry."""
    gap = data.get(CONF_GAP_HOURS)
    days = data.get(CONF_DAYS)
    return PassConfig(
        pass_id=str(data[CONF_PASS_ID]),
        work_mode=data.get(CONF_WORK_MODE) or None,
        fan_speed=data.get(CONF_FAN_SPEED) or None,
        start=_parse_time(data.get(CONF_START)),
        end=_parse_time(data.get(CONF_END)),
        forced=bool(data.get(CONF_FORCED, True)),
        gap=timedelta(hours=float(gap)) if gap else None,
        days=frozenset(WEEKDAYS.index(d) for d in days if d in WEEKDAYS)
        if days
        else None,
    )


@dataclass(frozen=True, slots=True)
class PassDone:
    """A pass done today."""

    pass_id: str
    at: datetime | None  # None for counts converted from older versions
    work_mode: str | None = None
    manual: bool = False  # started from a button or the panel


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
    passes: tuple[PassConfig, ...] = ()

    def get_pass(self, pass_id: str | None) -> PassConfig | None:
        """The pass with this id, if it is still in the program."""
        return next((p for p in self.passes if p.pass_id == pass_id), None)


@dataclass(slots=True)
class RoomState:
    """Live state of a room."""

    enabled: bool = True
    # None when the room has no sensors or all of them are unavailable.
    occupied: bool | None = None
    # When the room became empty (all sensors off); None if occupied/unknown.
    empty_since: datetime | None = None
    proxy_active: bool = False
    done_today: list[PassDone] = field(default_factory=list)
    # The last pass of the program done in the room (today or before).
    last_clean: datetime | None = None


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
    pass_id: str | None  # None: a manual cleaning that does not count
    work_mode: str | None
    fan_speed: str | None
    forced: bool  # deadline passed (or started by hand): clean even if occupied
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


def _at(now: datetime, t: time) -> datetime:
    return now.replace(hour=t.hour, minute=t.minute, second=t.second, microsecond=0)


def _local(now: datetime, moment: datetime) -> datetime:
    """Sensor timestamps are UTC: compare times and dates in `now`'s zone."""
    if moment.tzinfo is not None and now.tzinfo is not None:
        return moment.astimezone(now.tzinfo)
    return moment


def gap_end(now: datetime, p: PassConfig, st: RoomState) -> datetime | None:
    """When the minimum gap of `p` ends, if it has one and a pass was done."""
    if p.gap is None or st.last_clean is None:
        return None
    return _local(now, st.last_clean) + p.gap


def pass_states(
    cfg: RoomConfig,
    st: RoomState,
    now: datetime,
    *,
    active_pass_id: str | None = None,
    active_manual: bool = False,
) -> list[PassStatus]:
    """Status of every pass of the program today, in program order.

    `active_pass_id` is the pass being cleaned now; a manual job
    (`active_manual`) does not skip the earlier passes still pending.
    """
    today = now.date()
    done = {d.pass_id for d in st.done_today}
    statuses: list[PassStatus] = []
    for p in cfg.passes:
        if not p.applies(today):
            statuses.append(PassStatus.NOT_TODAY)
        elif p.pass_id in done:
            statuses.append(PassStatus.DONE)
        elif p.pass_id == active_pass_id:
            statuses.append(PassStatus.ACTIVE)
        else:
            statuses.append(PassStatus.PENDING)

    # (c) A later pass done (or started) by the planner skips the earlier ones.
    planned = {d.pass_id for d in st.done_today if not d.manual}
    if active_pass_id is not None and not active_manual:
        planned.add(active_pass_id)
    last = max(
        (i for i, p in enumerate(cfg.passes) if p.pass_id in planned), default=-1
    )
    for i in range(last):
        if statuses[i] is PassStatus.PENDING:
            statuses[i] = PassStatus.SKIPPED

    for i, p in enumerate(cfg.passes):
        if statuses[i] is not PassStatus.PENDING or p.end is None:
            continue
        deadline = _at(now, p.end)
        # (a) The window closed and the pass is not forced.
        if not p.forced and now >= deadline:
            statuses[i] = PassStatus.SKIPPED
            continue
        # (b) The minimum gap ends after the deadline: the gap wins.
        if (end := gap_end(now, p, st)) is not None and end > deadline:
            statuses[i] = PassStatus.SKIPPED
    return statuses


def _forced_now(p: PassConfig, now: datetime) -> bool:
    return p.is_forced and now >= _at(now, p.end)  # type: ignore[arg-type]


def candidate(
    cfg: RoomConfig, statuses: Sequence[PassStatus], now: datetime
) -> int | None:
    """Index of the pass the room works towards now.

    The first pending pass, unless it is not forced yet and a later pending
    pass has reached its forced deadline: that one goes first (and the
    earlier ones are skipped once it starts).
    """
    pending = [i for i, s in enumerate(statuses) if s is PassStatus.PENDING]
    if not pending:
        return None
    first = pending[0]
    if _forced_now(cfg.passes[first], now):
        return first
    for i in pending[1:]:
        if _forced_now(cfg.passes[i], now):
            return i
    return first


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
        statuses = pass_states(cfg, st, now)
        i = candidate(cfg, statuses, now)
        if i is None:
            result.statuses[cfg.room_id] = RoomStatus.DONE
            continue
        p = cfg.passes[i]
        if p.start is not None and now.time() < p.start:
            result.statuses[cfg.room_id] = RoomStatus.WAITING_WINDOW
            continue
        if (end := gap_end(now, p, st)) is not None and now < end:
            result.statuses[cfg.room_id] = RoomStatus.WAITING_GAP
            continue
        if quiet_hours:
            result.statuses[cfg.room_id] = RoomStatus.WAITING_QUIET_HOURS
            continue
        if not awake:
            result.statuses[cfg.room_id] = RoomStatus.WAITING_AWAKE
            continue

        forced = _forced_now(p, now)
        free = is_free(cfg, st, now)
        if not free and not forced:
            result.statuses[cfg.room_id] = RoomStatus.WAITING_OCCUPIED
            continue

        result.statuses[cfg.room_id] = (
            RoomStatus.READY if robot_ready else RoomStatus.WAITING_ROBOT
        )
        # Forced first, then the nearest deadline, the longest wait, the order.
        deadline = _at(now, p.end).timestamp() if p.end is not None else float("inf")
        last = (
            _local(now, st.last_clean).timestamp() if st.last_clean else float("-inf")
        )
        key = (0 if forced else 1, deadline, last, index)
        candidates.append(
            (
                key,
                Decision(
                    cfg.room_id,
                    p.pass_id,
                    p.work_mode,
                    p.fan_speed,
                    forced=forced,
                    quiet=forced and not free,
                ),
            )
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


def manual_target(
    cfg: RoomConfig,
    st: RoomState,
    now: datetime,
    work_mode: str | None,
    *,
    any_mode: bool = False,
) -> PassConfig | None:
    """The pass a manual cleaning with `work_mode` counts as, if any.

    The first pass of today, pending or skipped, with the same work mode
    (any work mode with `any_mode`: the robot has no work mode to choose).
    """
    for p, status in zip(cfg.passes, pass_states(cfg, st, now), strict=True):
        if status in (PassStatus.PENDING, PassStatus.SKIPPED) and (
            any_mode or p.work_mode == work_mode
        ):
            return p
    return None


# ------------------------------------------------------------------ outlook


class WaitReason(StrEnum):
    """What the next pass of a room is waiting for."""

    WINDOW = "window"  # start time of the pass
    GAP = "gap"  # minimum gap since the last pass
    QUIET_HOURS = "quiet_hours"
    AWAKE = "awake"  # wake-up check, time unknown
    EMPTY = "empty"  # room empty, not for long enough yet
    OCCUPIED = "occupied"  # someone is there: no time known until the deadline
    NOT_TODAY = "not_today"  # cannot start before the window closes or midnight


@dataclass(frozen=True, slots=True)
class RoomOutlook:
    """When the next pass of a room can start, as far as we can tell now.

    The presence sensors can change at any time: `earliest` assumes the room
    stays as it is now (empty rooms stay empty, occupied rooms stay occupied
    until their deadline).
    """

    pass_id: str | None  # next pass still due today
    position: int  # 1-based, among today's passes (0 without a next pass)
    total: int  # passes planned today
    done: int
    skipped: int
    work_mode: str | None
    earliest: datetime | None  # None: done, unknown, or not today
    reason: WaitReason | None  # what `earliest` waits for (None: can start now)
    free_at: datetime | None  # when the room counts as empty, if it stays so
    deadline: datetime | None  # when the pass is forced (or skipped)
    forced: bool  # the pass is forced at its deadline


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
    statuses = pass_states(cfg, st, now)
    today = [s for s in statuses if s is not PassStatus.NOT_TODAY]
    total = len(today)
    done = sum(1 for s in today if s is PassStatus.DONE)
    skipped = sum(1 for s in today if s is PassStatus.SKIPPED)
    i = candidate(cfg, statuses, now) if st.enabled else None
    if i is None:
        return RoomOutlook(
            None, 0, total, done, skipped, None, None, None, None, None, False
        )
    p = cfg.passes[i]
    position = sum(1 for s in statuses[: i + 1] if s is not PassStatus.NOT_TODAY)
    deadline = _at(now, p.end) if p.end is not None else None

    def result(
        earliest: datetime | None, reason: WaitReason | None, free_at: datetime | None
    ) -> RoomOutlook:
        return RoomOutlook(
            p.pass_id,
            position,
            total,
            done,
            skipped,
            p.work_mode,
            earliest,
            reason,
            free_at,
            deadline,
            p.is_forced,
        )

    # Time constraints: start of the window, minimum gap, quiet hours.
    start, reason = now, None
    if p.start is not None and _at(now, p.start) > start:
        start, reason = _at(now, p.start), WaitReason.WINDOW
    if (end := gap_end(now, p, st)) is not None and end > start:
        start, reason = end, WaitReason.GAP
    moved = _after_quiet(start, gcfg)
    if moved != start:
        start, reason = moved, WaitReason.QUIET_HOURS

    # Presence: the room must be empty long enough, unless the deadline passed.
    free_at: datetime | None = None
    occupied = False
    if cfg.occupancy_sensors:
        if st.occupied is False and st.empty_since is not None:
            free_at = _local(now, st.empty_since) + timedelta(minutes=cfg.empty_minutes)
        else:
            occupied = True
    elif cfg.proxy_sensors and not st.proxy_active:
        occupied = True

    options: list[tuple[datetime, WaitReason | None]] = []
    if not occupied:
        if free_at is not None and free_at > start:
            options.append((free_at, WaitReason.EMPTY))
        else:
            options.append((start, reason))
    if deadline is not None and p.is_forced:
        forced_at = max(start, deadline)
        options.append(
            (forced_at, reason if forced_at == start else WaitReason.OCCUPIED)
        )

    if not options:
        return result(None, WaitReason.OCCUPIED, free_at)
    earliest, reason = min(options, key=lambda c: c[0])
    if not awake and reason is None:
        reason = WaitReason.AWAKE
    if earliest.date() != now.date() or (
        deadline is not None and not p.is_forced and earliest >= deadline
    ):
        return result(None, WaitReason.NOT_TODAY, free_at)
    return result(earliest, reason, free_at)


def next_room(outlooks: dict[str, RoomOutlook], order: list[str]) -> str | None:
    """The room expected to be cleaned next: earliest start, then `plan()` priorities."""
    best: tuple | None = None
    best_id: str | None = None
    for index, room_id in enumerate(order):
        ol = outlooks.get(room_id)
        if ol is None or ol.earliest is None or ol.pass_id is None:
            continue
        forced = ol.forced and ol.deadline is not None and ol.earliest >= ol.deadline
        deadline = ol.deadline.timestamp() if ol.deadline else float("inf")
        key = (ol.earliest, 0 if forced else 1, deadline, index)
        if best is None or key < best:
            best, best_id = key, room_id
    return best_id
