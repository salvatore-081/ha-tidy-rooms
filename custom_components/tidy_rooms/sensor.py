"""Sensors: status of each room and of the robot job."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import TidyRoomsConfigEntry
from .engine import JobPhase, Room, TidyRoomsEngine
from .entity import TidyRoomsEntity, TidyRoomsRoomEntity
from .planner import PassStatus, RoomStatus

JOB_STATES = ["idle", *[p.value for p in JobPhase]]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TidyRoomsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    engine = entry.runtime_data
    async_add_entities([JobSensor(engine)])
    for room in engine.rooms.values():
        async_add_entities(
            [
                RoomStatusSensor(engine, room),
                PassesTodaySensor(engine, room),
                LastCleanSensor(engine, room),
            ],
            config_subentry_id=room.subentry_id,
        )


class JobSensor(TidyRoomsEntity, SensorEntity):
    """What the robot is doing for Tidy Rooms."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = JOB_STATES

    def __init__(self, engine: TidyRoomsEngine) -> None:
        """Initialize."""
        super().__init__(engine, "job")

    @property
    def native_value(self) -> str:
        """Job phase."""
        job = self.engine.job
        return job.phase.value if job else "idle"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Details of the job and of the plan."""
        job = self.engine.job
        attrs: dict[str, Any] = {
            "enabled": self.engine.enabled,
            "awake": self.engine.awake,
        }
        if job:
            attrs.update(
                room=self.engine.rooms[job.decision.room_id].config.name,
                work_mode=job.decision.work_mode,
                counts=job.decision.pass_id is not None,
                forced=job.decision.forced,
                quiet=job.decision.quiet or job.quiet_applied,
                started=job.started.isoformat(),
                attempts=job.attempts,
            )
        return attrs


def _today(engine: TidyRoomsEngine, room: Room) -> list[PassStatus]:
    """Statuses of the passes planned today."""
    return [
        s
        for s in engine.pass_states(room, dt_util.now())
        if s is not PassStatus.NOT_TODAY
    ]


class RoomStatusSensor(TidyRoomsRoomEntity, SensorEntity):
    """Why a room is waiting, or that it is done."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [s.value for s in RoomStatus]

    def __init__(self, engine: TidyRoomsEngine, room: Room) -> None:
        """Initialize."""
        super().__init__(engine, room, "status")

    @property
    def native_value(self) -> str | None:
        """Room status from the last plan."""
        status = self.engine.last_plan.statuses.get(self.room.subentry_id)
        return status.value if status else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Today's progress."""
        today = _today(self.engine, self.room)
        ol = self.engine.outlooks(dt_util.now())[self.room.subentry_id]
        return {
            "passes_done": today.count(PassStatus.DONE),
            "passes_total": len(today),
            "next_pass": ol.work_mode if ol.pass_id else None,
            "next_start": ol.earliest.isoformat() if ol.earliest else None,
            "occupied": self.room.state.occupied,
            "last_result": self.room.last_result,
        }


class PassesTodaySensor(TidyRoomsRoomEntity, SensorEntity):
    """How many passes of today's program are done."""

    def __init__(self, engine: TidyRoomsEngine, room: Room) -> None:
        """Initialize."""
        super().__init__(engine, room, "passes_today")

    @property
    def native_value(self) -> int:
        """Passes done today."""
        return _today(self.engine, self.room).count(PassStatus.DONE)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Passes planned and skipped today."""
        today = _today(self.engine, self.room)
        return {"total": len(today), "skipped": today.count(PassStatus.SKIPPED)}


class LastCleanSensor(TidyRoomsRoomEntity, SensorEntity):
    """When the room last got a pass of its program."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, engine: TidyRoomsEngine, room: Room) -> None:
        """Initialize."""
        super().__init__(engine, room, "last_clean")

    @property
    def native_value(self) -> datetime | None:
        """Timestamp."""
        return self.room.state.last_clean
