"""Tidy Rooms: clean each room when it is empty, with daily targets per room."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .engine import TidyRoomsEngine

PLATFORMS: list[Platform] = [Platform.BUTTON, Platform.SENSOR, Platform.SWITCH]

type TidyRoomsConfigEntry = ConfigEntry[TidyRoomsEngine]


async def async_setup_entry(hass: HomeAssistant, entry: TidyRoomsConfigEntry) -> bool:
    """Set up Tidy Rooms from a config entry."""
    engine = TidyRoomsEngine(hass, entry)
    entry.runtime_data = engine
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await engine.async_start()
    # Rooms added, edited or removed: rebuild everything.
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: TidyRoomsConfigEntry) -> None:
    hass.config_entries.async_schedule_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: TidyRoomsConfigEntry) -> bool:
    """Unload a config entry."""
    await entry.runtime_data.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
