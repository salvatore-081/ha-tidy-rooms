"""Buttons: clean a room now, one per work mode of the robot."""

from __future__ import annotations

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TidyRoomsConfigEntry
from .const import DOMAIN
from .engine import Room, TidyRoomsEngine
from .entity import TidyRoomsRoomEntity
from .schema import work_modes

KEY_PLAIN = "clean_now"
KEY_MODE = "clean_now_mode"


def _mode_prefix(room: Room) -> str:
    return f"{room.subentry_id}_{KEY_MODE}_"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TidyRoomsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up buttons."""
    engine = entry.runtime_data
    registry = er.async_get(hass)
    modes = work_modes(hass, engine.work_mode_entity)
    for room in engine.rooms.values():
        if not engine.work_mode_entity:
            buttons = [CleanNowButton(engine, room, None)]
        else:
            prefix = _mode_prefix(room)
            known = [
                e
                for e in er.async_entries_for_config_entry(registry, entry.entry_id)
                if e.domain == BUTTON_DOMAIN
                and e.platform == DOMAIN
                and e.unique_id.startswith(prefix)
            ]
            if modes:
                # The robot's options are known: drop the buttons of old ones.
                for e in known:
                    if e.unique_id.removeprefix(prefix) not in modes:
                        registry.async_remove(e.entity_id)
                room_modes = modes
            else:
                # Not known yet (robot's integration still loading): keep the
                # buttons already registered.
                room_modes = [e.unique_id.removeprefix(prefix) for e in known]
            buttons = [CleanNowButton(engine, room, mode) for mode in room_modes]
        async_add_entities(buttons, config_subentry_id=room.subentry_id)


class CleanNowButton(TidyRoomsRoomEntity, ButtonEntity):
    """Clean the room now with a work mode, even if someone is there."""

    def __init__(self, engine: TidyRoomsEngine, room: Room, mode: str | None) -> None:
        """Initialize: `mode` None means the robot has no work mode entity."""
        key = KEY_PLAIN if mode is None else f"{KEY_MODE}_{mode}"
        super().__init__(engine, room, key)
        self._mode = mode
        if mode is not None:
            # Raw option in the name: entity ids must not depend on translations.
            self._attr_translation_key = KEY_MODE
            self._attr_translation_placeholders = {"mode": mode}

    async def async_press(self) -> None:
        """Start the job; it counts as today's matching pass when done."""
        await self.engine.async_clean_now(
            self.room.subentry_id, self._mode, use_default=False
        )
