"""Form schemas and validation, shared by the config flows and the panel."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.components.event import DOMAIN as EVENT_DOMAIN
from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import selector

from .const import (
    CONF_AREA,
    CONF_BATTERY_ENTITY,
    CONF_CLEAN_ACTION,
    CONF_EMPTY_MINUTES,
    CONF_FINISHED_EVENT,
    CONF_FULL_DEADLINE,
    CONF_FULL_MODE_OPTION,
    CONF_FULL_PER_DAY,
    CONF_JOB_DONE_DELAY,
    CONF_JOB_ENTITY,
    CONF_MIN_BATTERY,
    CONF_MIN_GAP_HOURS,
    CONF_NORMAL_FAN_SPEED,
    CONF_OCCUPANCY_SENSORS,
    CONF_PROXY_SENSORS,
    CONF_QUIET_END,
    CONF_QUIET_FAN_SPEED,
    CONF_QUIET_START,
    CONF_START_TIMEOUT,
    CONF_VACUUM,
    CONF_VACUUM_DEADLINE,
    CONF_VACUUM_MODE_OPTION,
    CONF_VACUUM_PER_DAY,
    CONF_WAKE_DAYS,
    CONF_WAKE_MINUTES,
    CONF_WAKE_SENSORS,
    CONF_WORK_MODE_ENTITY,
    DEFAULT_EMPTY_MINUTES,
    DEFAULT_FULL_DEADLINE,
    DEFAULT_FULL_PER_DAY,
    DEFAULT_MIN_GAP_HOURS,
    DEFAULT_VACUUM_DEADLINE,
    DEFAULT_VACUUM_PER_DAY,
    SUBENTRY_ROOM,
    WEEKDAYS,
)

OCCUPANCY_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=BINARY_SENSOR_DOMAIN, multiple=True)
)

ROOM_DEFAULTS: dict[str, Any] = {
    CONF_EMPTY_MINUTES: DEFAULT_EMPTY_MINUTES,
    CONF_FULL_PER_DAY: DEFAULT_FULL_PER_DAY,
    CONF_VACUUM_PER_DAY: DEFAULT_VACUUM_PER_DAY,
    CONF_MIN_GAP_HOURS: DEFAULT_MIN_GAP_HOURS,
    CONF_FULL_DEADLINE: DEFAULT_FULL_DEADLINE,
    CONF_VACUUM_DEADLINE: DEFAULT_VACUUM_DEADLINE,
}

# Settings of the panel, by section. The options flow shows the first three
# in its first step and "robot" in the second (its choices depend on them).
SECTION_SCHEDULE = "schedule"
SECTION_WAKE = "wake"
SECTION_SIGNALS = "signals"
SECTION_ROBOT = "robot"


def minutes_selector(max_value: int) -> selector.NumberSelector:
    """Whole minutes, typed in a box."""
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
            max=max_value,
            step=1,
            unit_of_measurement="min",
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def count_selector(max_value: int) -> selector.NumberSelector:
    """A small count, typed in a box."""
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0, max=max_value, step=1, mode=selector.NumberSelectorMode.BOX
        )
    )


def _dropdown(options: list[str]) -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options, mode=selector.SelectSelectorMode.DROPDOWN
        )
    )


# ------------------------------------------------------------------ rooms


def room_schema() -> vol.Schema:
    """Fields of a room."""
    return vol.Schema(
        {
            vol.Required(CONF_AREA): selector.AreaSelector(),
            vol.Optional(CONF_OCCUPANCY_SENSORS): OCCUPANCY_SELECTOR,
            vol.Optional(CONF_PROXY_SENSORS): OCCUPANCY_SELECTOR,
            vol.Required(CONF_EMPTY_MINUTES): minutes_selector(240),
            vol.Required(CONF_FULL_PER_DAY): count_selector(3),
            vol.Required(CONF_VACUUM_PER_DAY): count_selector(6),
            vol.Required(CONF_MIN_GAP_HOURS): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=24,
                    step=0.5,
                    unit_of_measurement="h",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(CONF_FULL_DEADLINE): selector.TimeSelector(),
            vol.Optional(CONF_VACUUM_DEADLINE): selector.TimeSelector(),
            vol.Optional(CONF_CLEAN_ACTION): selector.ActionSelector(),
        }
    )


def room_title(hass: HomeAssistant, data: dict[str, Any]) -> str:
    """A room is named after its area."""
    area = ar.async_get(hass).async_get_area(data[CONF_AREA])
    return area.name if area else data[CONF_AREA]


def validate_room(
    entry: ConfigEntry, data: dict[str, Any], current: str | None
) -> dict[str, str]:
    """Errors by field (translation keys), empty when the room is valid."""
    errors: dict[str, str] = {}
    for sub in entry.subentries.values():
        if (
            sub.subentry_type == SUBENTRY_ROOM
            and sub.subentry_id != current
            and sub.data.get(CONF_AREA) == data[CONF_AREA]
        ):
            errors[CONF_AREA] = "area_already_configured"
    if data.get(CONF_OCCUPANCY_SENSORS) and data.get(CONF_PROXY_SENSORS):
        errors[CONF_PROXY_SENSORS] = "proxy_with_occupancy"
    if int(data[CONF_VACUUM_PER_DAY]) < int(data[CONF_FULL_PER_DAY]):
        errors[CONF_VACUUM_PER_DAY] = "vacuum_less_than_full"
    return errors


# --------------------------------------------------------------- settings


def settings_sections(
    hass: HomeAssistant, entry: ConfigEntry, work_mode_entity: str | None
) -> dict[str, vol.Schema]:
    """Fields of the global settings, by section.

    Fan speeds come from the robot; work modes from `work_mode_entity`, so
    the robot section changes when that entity changes.
    """
    sections = {
        SECTION_SCHEDULE: vol.Schema(
            {
                vol.Optional(CONF_QUIET_START): selector.TimeSelector(),
                vol.Optional(CONF_QUIET_END): selector.TimeSelector(),
                vol.Required(CONF_MIN_BATTERY): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=100, step=5, unit_of_measurement="%"
                    )
                ),
            }
        ),
        SECTION_WAKE: vol.Schema(
            {
                vol.Optional(CONF_WAKE_SENSORS): OCCUPANCY_SELECTOR,
                vol.Required(CONF_WAKE_MINUTES): minutes_selector(240),
                vol.Optional(CONF_WAKE_DAYS): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=WEEKDAYS, multiple=True, translation_key="weekday"
                    )
                ),
            }
        ),
        SECTION_SIGNALS: vol.Schema(
            {
                vol.Optional(CONF_WORK_MODE_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=SELECT_DOMAIN)
                ),
                vol.Optional(CONF_BATTERY_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=SENSOR_DOMAIN, device_class="battery"
                    )
                ),
                vol.Optional(CONF_JOB_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=BINARY_SENSOR_DOMAIN)
                ),
                vol.Optional(CONF_FINISHED_EVENT): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=EVENT_DOMAIN)
                ),
                vol.Required(CONF_START_TIMEOUT): minutes_selector(30),
                vol.Required(CONF_JOB_DONE_DELAY): minutes_selector(30),
            }
        ),
    }

    robot: dict[vol.Marker, Any] = {}
    vacuum = hass.states.get(entry.data[CONF_VACUUM])
    fan_speeds = list(vacuum.attributes.get("fan_speed_list") or []) if vacuum else []
    if fan_speeds:
        robot[vol.Optional(CONF_NORMAL_FAN_SPEED)] = _dropdown(fan_speeds)
        robot[vol.Optional(CONF_QUIET_FAN_SPEED)] = _dropdown(fan_speeds)
    if work_mode_entity:
        mode_state = hass.states.get(work_mode_entity)
        modes = list(mode_state.attributes.get("options") or []) if mode_state else []
        if modes:
            robot[vol.Optional(CONF_FULL_MODE_OPTION)] = _dropdown(modes)
            robot[vol.Optional(CONF_VACUUM_MODE_OPTION)] = _dropdown(modes)
    sections[SECTION_ROBOT] = vol.Schema(robot)
    return sections


def settings_keys() -> set[str]:
    """Every option the settings can set (the rest of the options is kept)."""
    return {
        CONF_QUIET_START,
        CONF_QUIET_END,
        CONF_MIN_BATTERY,
        CONF_WAKE_SENSORS,
        CONF_WAKE_MINUTES,
        CONF_WAKE_DAYS,
        CONF_WORK_MODE_ENTITY,
        CONF_BATTERY_ENTITY,
        CONF_JOB_ENTITY,
        CONF_FINISHED_EVENT,
        CONF_START_TIMEOUT,
        CONF_JOB_DONE_DELAY,
        CONF_NORMAL_FAN_SPEED,
        CONF_QUIET_FAN_SPEED,
        CONF_FULL_MODE_OPTION,
        CONF_VACUUM_MODE_OPTION,
    }
