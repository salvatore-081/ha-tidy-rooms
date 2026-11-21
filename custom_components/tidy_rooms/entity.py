"""Base entities for Tidy Rooms."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .engine import Room, TidyRoomsEngine


class TidyRoomsEntity(Entity):
    """Entity of the whole entry (one device per robot)."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, engine: TidyRoomsEngine, key: str) -> None:
        """Initialize."""
        self.engine = engine
        self._attr_translation_key = key
        self._attr_unique_id = f"{engine.entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, engine.entry.entry_id)},
            name=f"Tidy Rooms {engine.entry.title}",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        """Follow engine updates."""
        self.async_on_remove(
            async_dispatcher_connect(self.hass, self.engine.signal, self._on_update)
        )

    @callback
    def _on_update(self) -> None:
        self.async_write_ha_state()


class TidyRoomsRoomEntity(TidyRoomsEntity):
    """Entity of one room (one device per room, in the room's area)."""

    def __init__(self, engine: TidyRoomsEngine, room: Room, key: str) -> None:
        """Initialize."""
        super().__init__(engine, key)
        self.room = room
        self._attr_unique_id = f"{room.subentry_id}_{key}"
        area = ar.async_get(engine.hass).async_get_area(room.area_id)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, room.subentry_id)},
            name=f"Tidy Rooms {room.config.name}",
            suggested_area=area.name if area else None,
            entry_type=DeviceEntryType.SERVICE,
            via_device=(DOMAIN, engine.entry.entry_id),
        )
