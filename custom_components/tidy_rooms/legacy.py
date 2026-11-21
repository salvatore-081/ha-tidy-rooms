"""Conversion of the data of Tidy Rooms 0.3.0 and earlier to cleaning programs.

Up to 0.3.0 a room had two kinds of pass with a daily count each: "full"
(vacuum, then mop) and "vacuum", one deadline per kind and a minimum gap
between vacuum passes (a full pass counts as a vacuum pass too, but does not
wait for the gap). The same rules as a program: the full passes first, then
the vacuum-only ones with the gap, all forced at their deadline.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import uuid4

from .const import (
    CONF_END,
    CONF_FAN_SPEED,
    CONF_FORCED,
    CONF_FULL_DEADLINE,
    CONF_FULL_MODE_OPTION,
    CONF_FULL_PER_DAY,
    CONF_GAP_HOURS,
    CONF_MIN_GAP_HOURS,
    CONF_PASS_ID,
    CONF_ROOM_FAN_SPEED,
    CONF_ROOM_FULL_MODE,
    CONF_ROOM_VACUUM_MODE,
    CONF_VACUUM_DEADLINE,
    CONF_VACUUM_MODE_OPTION,
    CONF_VACUUM_PER_DAY,
    CONF_WORK_MODE,
)
from .planner import PassDone

KIND_FULL = "full"
KIND_VACUUM = "vacuum"

# Keys of a room that the program replaces.
LEGACY_ROOM_KEYS = (
    CONF_FULL_PER_DAY,
    CONF_VACUUM_PER_DAY,
    CONF_MIN_GAP_HOURS,
    CONF_FULL_DEADLINE,
    CONF_VACUUM_DEADLINE,
    CONF_ROOM_FULL_MODE,
    CONF_ROOM_VACUUM_MODE,
)
# Options that the program replaces (each pass has its own work mode).
LEGACY_OPTION_KEYS = (CONF_FULL_MODE_OPTION, CONF_VACUUM_MODE_OPTION)


def new_pass_id() -> str:
    """A short id for a new pass, stable for the life of the pass."""
    return uuid4().hex[:8]


def legacy_program(
    room: Mapping[str, Any], options: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """The program equivalent to the counts and deadlines of a 0.3.0 room.

    The pass ids tell the old kind ("full-1", "vacuum-1", …): the saved counts
    of today and a job saved by 0.3.0 are converted with them.
    """
    full = int(room.get(CONF_FULL_PER_DAY, 0) or 0)
    vacuum = max(int(room.get(CONF_VACUUM_PER_DAY, 0) or 0) - full, 0)
    fan = room.get(CONF_ROOM_FAN_SPEED) or None
    gap = float(room.get(CONF_MIN_GAP_HOURS, 0) or 0)

    def one(pass_id: str, mode: str | None, end: str | None, gap_hours: float) -> dict:
        p: dict[str, Any] = {CONF_PASS_ID: pass_id, CONF_FORCED: True}
        if mode:
            p[CONF_WORK_MODE] = mode
        if fan:
            p[CONF_FAN_SPEED] = fan
        if end:
            p[CONF_END] = end
        if gap_hours:
            p[CONF_GAP_HOURS] = gap_hours
        return p

    full_mode = room.get(CONF_ROOM_FULL_MODE) or options.get(CONF_FULL_MODE_OPTION)
    vacuum_mode = room.get(CONF_ROOM_VACUUM_MODE) or options.get(
        CONF_VACUUM_MODE_OPTION
    )
    return [
        one(f"{KIND_FULL}-{n}", full_mode, room.get(CONF_FULL_DEADLINE), 0)
        for n in range(1, full + 1)
    ] + [
        one(f"{KIND_VACUUM}-{n}", vacuum_mode, room.get(CONF_VACUUM_DEADLINE), gap)
        for n in range(1, vacuum + 1)
    ]


def legacy_kind(pass_id: str | None) -> str | None:
    """The 0.3.0 kind of a converted pass, from its id."""
    kind, _, number = (pass_id or "").partition("-")
    return kind if kind in (KIND_FULL, KIND_VACUUM) and number.isdigit() else None


def legacy_done(
    pass_ids: Sequence[str],
    full_today: int,
    vacuum_today: int,
    last: datetime | None,
) -> list[PassDone]:
    """Today's passes done, from the 0.3.0 counts (a full pass counted twice).

    `pass_ids` are the ids of the room's program; only converted passes
    ("full-1", "vacuum-1", …) are marked. Only the time of the last one is
    known: it goes on the last pass marked. They count as manual: 0.3.0 had
    no order between passes (a "clean now" button could do a vacuum pass
    before the full one), so they must not skip the earlier passes still due.
    """
    full_ids = [p for p in pass_ids if legacy_kind(p) == KIND_FULL]
    vacuum_ids = [p for p in pass_ids if legacy_kind(p) == KIND_VACUUM]
    ids = (
        full_ids[: max(full_today, 0)] + vacuum_ids[: max(vacuum_today - full_today, 0)]
    )
    return [
        PassDone(pass_id, last if i == len(ids) - 1 else None, manual=True)
        for i, pass_id in enumerate(ids)
    ]
