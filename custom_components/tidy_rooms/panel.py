"""Sidebar panel and dashboard card."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import (
    add_extra_js_url,
    async_register_built_in_panel,
    async_remove_panel,
    remove_extra_js_url,
)
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).parent / "frontend"
PANEL_FILE = "tidy-rooms-panel.js"
CARD_FILE = "tidy-rooms-card.js"
STATIC_URL = "/tidy_rooms_files"
PANEL_URL_PATH = "tidy-rooms"
PANEL_ELEMENT = "tidy-rooms-panel"

DATA_PANEL = f"{DOMAIN}_panel"


async def async_register(hass: HomeAssistant) -> None:
    """Register the panel and the card once (several entries share them)."""
    if hass.data.get(DATA_PANEL) is not None:
        return
    if "frontend" not in hass.config.components or hass.http is None:
        return  # no user interface (tests, minimal setups)
    panel_js = FRONTEND_DIR / PANEL_FILE
    card_js = FRONTEND_DIR / CARD_FILE
    if not panel_js.exists():
        # Installed from the source tree instead of a release zip.
        _LOGGER.warning(
            "Tidy Rooms panel not found at %s: install a release to get the "
            "panel and the card; the integration works without them",
            panel_js,
        )
        hass.data[DATA_PANEL] = ""
        return

    version = (await async_get_integration(hass, DOMAIN)).version
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(FRONTEND_DIR), False)]
        )
    except RuntimeError:
        _LOGGER.debug("Tidy Rooms static path already registered")

    async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title="Tidy Rooms",
        sidebar_icon="mdi:robot-vacuum",
        frontend_url_path=PANEL_URL_PATH,
        require_admin=True,
        config={
            "_panel_custom": {
                "name": PANEL_ELEMENT,
                "embed_iframe": False,
                "trust_external": False,
                "js_url": f"{STATIC_URL}/{PANEL_FILE}?v={version}",
            }
        },
    )
    card_url = ""
    if card_js.exists():
        card_url = f"{STATIC_URL}/{CARD_FILE}?v={version}"
        add_extra_js_url(hass, card_url)
    hass.data[DATA_PANEL] = card_url or "panel"


def async_unregister(hass: HomeAssistant) -> None:
    """Remove the panel and the card (last entry unloaded)."""
    registered = hass.data.pop(DATA_PANEL, None)
    if not registered:
        return
    async_remove_panel(hass, PANEL_URL_PATH)
    if registered.startswith(STATIC_URL):
        remove_extra_js_url(hass, registered)
