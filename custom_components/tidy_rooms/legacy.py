"""Conversion of the data of Tidy Rooms 0.3.0 and earlier to cleaning programs.

Up to 0.3.0 a room had two kinds of pass with a daily count each: "full"
(vacuum, then mop) and "vacuum", one deadline per kind and a minimum gap
between vacuum passes (a full pass counts as a vacuum pass too, but does not
wait for the gap). The same rules as a program: the full passes first, then
the vacuum-only ones with the gap, all forced at their deadline.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
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
from .program import PassDone

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
    """A short id, stable for the life of the pass."""
    return uuid4().hex[:8]


def legacy_program(
    room: Mapping[str, Any],
    options: Mapping[str, Any],
    new_id: Callable[[], str] = new_pass_id,
) -> list[dict[str, Any]]:
    """The program equivalent to the counts and deadlines of a 0.3.0 room.

    The pass dicts carry a private "_kind" key ("full"/"vacuum"), used to
    convert the saved counts; `strip_kinds` removes it before saving.
    """
    full = int(room.get(CONF_FULL_PER_DAY, 0) or 0)
    vacuum = max(int(room.get(CONF_VACUUM_PER_DAY, 0) or 0) - full, 0)
    fan = room.get(CONF_ROOM_FAN_SPEED) or None
    gap = float(room.get(CONF_MIN_GAP_HOURS, 0) or 0)

    def one(kind: str, mode: str | None, end: str | None, gap_hours: float) -> dict:
        p: dict[str, Any] = {CONF_PASS_ID: new_id(), CONF_FORCED: True, "_kind": kind}
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
        one(KIND_FULL, full_mode, room.get(CONF_FULL_DEADLINE), 0) for _ in range(full)
    ] + [
        one(KIND_VACUUM, vacuum_mode, room.get(CONF_VACUUM_DEADLINE), gap)
        for _ in range(vacuum)
    ]


def strip_kinds(passes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The passes as saved, without the private "_kind" key."""
    return [{k: v for k, v in p.items() if k != "_kind"} for p in passes]


def legacy_done(
    passes: list[dict[str, Any]],
    full_today: int,
    vacuum_today: int,
    last: datetime | None,
) -> list[PassDone]:
    """Today's passes done, from the 0.3.0 counts (a full pass counted twice).

    Only the time of the last one is known: it goes on the last pass marked.
    They count as manual: 0.3.0 had no order between passes (a "clean now"
    button could do a vacuum pass before the full one), so they must not skip
    the earlier passes still due.
    """
    full_ids = [p[CONF_PASS_ID] for p in passes if p.get("_kind") == KIND_FULL]
    vacuum_ids = [p[CONF_PASS_ID] for p in passes if p.get("_kind") == KIND_VACUUM]
    done_full = full_ids[: max(full_today, 0)]
    done_vacuum = vacuum_ids[: max(vacuum_today - full_today, 0)]
    ids = done_full + done_vacuum
    return [
        PassDone(pass_id, last if i == len(ids) - 1 else None, manual=True)
        for i, pass_id in enumerate(ids)
    ]


def legacy_kind(passes: list[dict[str, Any]], pass_id: str | None) -> str | None:
    """The 0.3.0 kind of a converted pass."""
    return next((p.get("_kind") for p in passes if p[CONF_PASS_ID] == pass_id), None)
