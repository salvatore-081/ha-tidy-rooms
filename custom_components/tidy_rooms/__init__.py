"""Tidy Rooms: clean each room when it is empty, with daily targets per room."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from . import panel, websocket_api
from .const import (
    CONF_PASSES,
    CONF_ROOM_FAN_SPEED,
    CONF_ROOM_ORDER,
    DOMAIN,
    STORAGE_VERSION,
    SUBENTRY_ROOM,
)
from .engine import TidyRoomsEngine
from .history import JobHistory
from .legacy import LEGACY_OPTION_KEYS, LEGACY_ROOM_KEYS, legacy_program

PLATFORMS: list[Platform] = [Platform.BUTTON, Platform.SENSOR, Platform.SWITCH]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type TidyRoomsConfigEntry = ConfigEntry[TidyRoomsEngine]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the WebSocket API of the panel."""
    websocket_api.async_register(hass)
    return True


# Entities of 0.3.0 that cleaning programs replace (unique id suffixes).
LEGACY_ENTITIES = ("clean_now_full", "clean_now_vacuum", "last_full", "last_vacuum")


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Version 1 (up to 0.3.0) to 2: counts per kind become cleaning programs.

    Safe to run again after an interruption: rooms that already have a
    program are left alone, and the version changes last.
    """
    if entry.version > 2:
        return False  # saved by a newer version
    if entry.version == 1:
        registry = er.async_get(hass)
        for sub in list(entry.subentries.values()):
            if sub.subentry_type != SUBENTRY_ROOM:
                continue
            if CONF_PASSES not in sub.data:
                data = {
                    k: v
                    for k, v in sub.data.items()
                    if k not in LEGACY_ROOM_KEYS and k != CONF_ROOM_FAN_SPEED
                }
                data[CONF_PASSES] = legacy_program(sub.data, entry.options)
                hass.config_entries.async_update_subentry(entry, sub, data=data)
            for key in LEGACY_ENTITIES:
                for domain in ("button", "sensor"):
                    entity_id = registry.async_get_entity_id(
                        domain, DOMAIN, f"{sub.subentry_id}_{key}"
                    )
                    if entity_id:
                        registry.async_remove(entity_id)
        options = {
            k: v for k, v in entry.options.items() if k not in LEGACY_OPTION_KEYS
        }
        hass.config_entries.async_update_entry(entry, options=options, version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: TidyRoomsConfigEntry) -> bool:
    """Set up Tidy Rooms from a config entry."""
    engine = TidyRoomsEngine(hass, entry)
    entry.runtime_data = engine
    # The robot's device first: the room devices hang from it (via_device_id).
    engine.device_id = (
        dr.async_get(hass)
        .async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Tidy Rooms {entry.title}",
            entry_type=dr.DeviceEntryType.SERVICE,
        )
        .id
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await engine.async_start()
    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))
    await panel.async_register(hass)
    return True


async def _async_entry_updated(
    hass: HomeAssistant, entry: TidyRoomsConfigEntry
) -> None:
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
    # The panel stays through a reload (a room, a program or the settings
    # saved): removing it, even for a moment, sends the browser away from it.
    # It goes when the last entry is disabled or removed.
    if entry.disabled_by is not None and not _panel_needed(hass, entry):
        panel.async_unregister(hass)
    return unloaded


def _panel_needed(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Whether another entry, not disabled, still uses the panel."""
    return any(
        e.entry_id != entry.entry_id and e.disabled_by is None
        for e in hass.config_entries.async_entries(DOMAIN)
    )


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the saved state, the job log and, if last, the panel of a removed entry."""
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()
    await JobHistory(hass, entry.entry_id).async_remove()
    if not _panel_needed(hass, entry):
        panel.async_unregister(hass)
