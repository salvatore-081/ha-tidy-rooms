"""Sensors: status of each room and of the robot job."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TidyRoomsConfigEntry
from .engine import JobPhase, Room, TidyRoomsEngine
from .entity import TidyRoomsEntity, TidyRoomsRoomEntity
from .planner import RoomStatus

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
                LastCleanSensor(engine, room, "last_full"),
                LastCleanSensor(engine, room, "last_vacuum"),
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
                kind=job.decision.kind.value,
                forced=job.decision.forced,
                quiet=job.decision.quiet or job.quiet_applied,
                started=job.started.isoformat(),
                attempts=job.attempts,
            )
        return attrs


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
        cfg, st = self.room.config, self.room.state
        return {
            "full_today": st.full_today,
            "full_per_day": cfg.full_per_day,
            "vacuum_today": st.vacuum_today,
            "vacuum_per_day": cfg.vacuum_per_day,
            "occupied": st.occupied,
            "last_result": self.room.last_result,
        }


class LastCleanSensor(TidyRoomsRoomEntity, SensorEntity):
    """When the room last got a pass of a kind."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, engine: TidyRoomsEngine, room: Room, key: str) -> None:
        """Initialize."""
        super().__init__(engine, room, key)
        self._key = key

    @property
    def native_value(self) -> datetime | None:
        """Timestamp."""
        return getattr(self.room.state, self._key)
