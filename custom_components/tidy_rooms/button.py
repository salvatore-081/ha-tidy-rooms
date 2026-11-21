"""Buttons: clean a room now."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TidyRoomsConfigEntry
from .engine import Room, TidyRoomsEngine
from .entity import TidyRoomsRoomEntity
from .planner import CleanKind


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TidyRoomsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up buttons."""
    engine = entry.runtime_data
    for room in engine.rooms.values():
        async_add_entities(
            [
                CleanNowButton(engine, room, CleanKind.FULL),
                CleanNowButton(engine, room, CleanKind.VACUUM),
            ],
            config_subentry_id=room.subentry_id,
        )


class CleanNowButton(TidyRoomsRoomEntity, ButtonEntity):
    """Clean the room now, even if someone is there."""

    def __init__(self, engine: TidyRoomsEngine, room: Room, kind: CleanKind) -> None:
        """Initialize."""
        super().__init__(engine, room, f"clean_now_{kind.value}")
        self._kind = kind

    async def async_press(self) -> None:
        """Start the job; it counts towards today's targets when done."""
        await self.engine.async_clean_now(self.room.subentry_id, self._kind)
