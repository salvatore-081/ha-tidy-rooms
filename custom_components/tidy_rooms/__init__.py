"""Tidy Rooms: clean each room when it is empty, with daily targets per room."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from . import panel, websocket_api
from .const import CONF_ROOM_ORDER, DOMAIN, STORAGE_VERSION
from .engine import TidyRoomsEngine
from .history import JobHistory

PLATFORMS: list[Platform] = [Platform.BUTTON, Platform.SENSOR, Platform.SWITCH]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type TidyRoomsConfigEntry = ConfigEntry[TidyRoomsEngine]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the WebSocket API of the panel."""
    websocket_api.async_register(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: TidyRoomsConfigEntry) -> bool:
    """Set up Tidy Rooms from a config entry."""
    engine = TidyRoomsEngine(hass, entry)
    entry.runtime_data = engine
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await engine.async_start()
    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))
    await panel.async_register(hass)
    return True


async def _async_entry_updated(hass: HomeAssistant, entry: TidyRoomsConfigEntry) -> None:
    """Rooms or settings changed: rebuild everything, unless only the order did."""
    engine = entry.runtime_data
    if TidyRoomsEngine.config_key(entry) == engine.loaded_config:
        engine.apply_order(entry.options.get(CONF_ROOM_ORDER) or [])
        return
    hass.config_entries.async_schedule_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: TidyRoomsConfigEntry) -> bool:
    """Unload a config entry."""
    await entry.runtime_data.async_stop()
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    others = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.entry_id != entry.entry_id and e.state is ConfigEntryState.LOADED
    ]
    if not others:
        panel.async_unregister(hass)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the saved state and the job log of a removed entry."""
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()
    await JobHistory(hass, entry.entry_id).async_remove()
