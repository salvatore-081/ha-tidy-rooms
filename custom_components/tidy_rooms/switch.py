"""Switches: pause the whole automation or a single room."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TidyRoomsConfigEntry
from .engine import Room, TidyRoomsEngine
from .entity import TidyRoomsEntity, TidyRoomsRoomEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TidyRoomsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up switches."""
    engine = entry.runtime_data
    async_add_entities([EnabledSwitch(engine)])
    for room in engine.rooms.values():
        async_add_entities(
            [RoomEnabledSwitch(engine, room)], config_subentry_id=room.subentry_id
        )


class EnabledSwitch(TidyRoomsEntity, SwitchEntity):
    """Automatic cleaning on or off (a job already running is not stopped)."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, engine: TidyRoomsEngine) -> None:
        """Initialize."""
        super().__init__(engine, "enabled")

    @property
    def is_on(self) -> bool:
        """Enabled."""
        return self.engine.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Resume."""
        await self.engine.async_set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Pause."""
        await self.engine.async_set_enabled(False)


class RoomEnabledSwitch(TidyRoomsRoomEntity, SwitchEntity):
    """Include the room in automatic cleaning."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, engine: TidyRoomsEngine, room: Room) -> None:
        """Initialize."""
        super().__init__(engine, room, "room_enabled")

    @property
    def is_on(self) -> bool:
        """Enabled."""
        return self.room.state.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Include the room."""
        await self.engine.async_set_room_enabled(self.room.subentry_id, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Skip the room."""
        await self.engine.async_set_room_enabled(self.room.subentry_id, False)
