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
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import (
    CONF_AREA,
    CONF_BATTERY_ENTITY,
    CONF_CLEAN_ACTION,
    CONF_DAYS,
    CONF_EMPTY_MINUTES,
    CONF_END,
    CONF_FAN_SPEED,
    CONF_FINISHED_EVENT,
    CONF_FORCED,
    CONF_GAP_HOURS,
    CONF_JOB_DONE_DELAY,
    CONF_JOB_ENTITY,
    CONF_MIN_BATTERY,
    CONF_NORMAL_FAN_SPEED,
    CONF_OCCUPANCY_SENSORS,
    CONF_PASS_ID,
    CONF_PASSES,
    CONF_PROXY_SENSORS,
    CONF_QUIET_END,
    CONF_QUIET_FAN_SPEED,
    CONF_QUIET_START,
    CONF_RESTORE_SETTINGS,
    CONF_START,
    CONF_START_TIMEOUT,
    CONF_VACUUM,
    CONF_WAKE_DAYS,
    CONF_WAKE_MINUTES,
    CONF_WAKE_SENSORS,
    CONF_WORK_MODE,
    CONF_WORK_MODE_ENTITY,
    DEFAULT_EMPTY_MINUTES,
    MAX_PASSES,
    SUBENTRY_ROOM,
    WEEKDAYS,
)
from .legacy import new_pass_id

OCCUPANCY_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=BINARY_SENSOR_DOMAIN, multiple=True)
)

ROOM_DEFAULTS: dict[str, Any] = {CONF_EMPTY_MINUTES: DEFAULT_EMPTY_MINUTES}
PASS_DEFAULTS: dict[str, Any] = {CONF_FORCED: True}

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


def _dropdown(options: list[str]) -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options, mode=selector.SelectSelectorMode.DROPDOWN
        )
    )


def fan_speeds(hass: HomeAssistant, entry: ConfigEntry) -> list[str]:
    """Fan speeds the robot offers (empty if it reports none or is missing)."""
    vacuum = hass.states.get(entry.data[CONF_VACUUM])
    return list(vacuum.attributes.get("fan_speed_list") or []) if vacuum else []


def work_modes(hass: HomeAssistant, work_mode_entity: str | None) -> list[str]:
    """Options of the robot's work mode select entity (empty if unknown).

    From the entity registry first: at startup the robot's integration may
    not have set its state yet.
    """
    if not work_mode_entity:
        return []
    entry = er.async_get(hass).async_get(work_mode_entity)
    if entry is not None and (options := (entry.capabilities or {}).get("options")):
        return list(options)
    state = hass.states.get(work_mode_entity)
    return list(state.attributes.get("options") or []) if state else []


# ------------------------------------------------------------------ rooms


def room_schema() -> vol.Schema:
    """Fields of a room (its program is edited apart, pass by pass)."""
    return vol.Schema(
        {
            vol.Required(CONF_AREA): selector.AreaSelector(),
            vol.Optional(CONF_OCCUPANCY_SENSORS): OCCUPANCY_SELECTOR,
            vol.Optional(CONF_PROXY_SENSORS): OCCUPANCY_SELECTOR,
            vol.Required(CONF_EMPTY_MINUTES): minutes_selector(240),
            vol.Optional(CONF_CLEAN_ACTION): selector.ActionSelector(),
        }
    )


def room_keys() -> set[str]:
    """Every field of the room form (the rest of the room data is kept)."""
    return {str(key) for key in room_schema().schema}


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
    return errors


def merge_room(current: dict[str, Any] | None, form: dict[str, Any]) -> dict[str, Any]:
    """New room data: the form's fields, the rest (the program) as it was.

    Optional fields left empty in the form are not in `form`: they go away.
    """
    kept = {k: v for k, v in (current or {}).items() if k not in room_keys()}
    kept.setdefault(CONF_PASSES, [])
    return {**kept, **form}


# ----------------------------------------------------------------- passes


def pass_schema(
    hass: HomeAssistant,
    entry: ConfigEntry,
    saved: list[dict[str, Any]] | None = None,
) -> vol.Schema:
    """Fields of a pass of the program.

    Work modes and fan speeds come from the robot; values already saved stay
    among the choices, so a robot that is unavailable now does not lose them.
    """

    def choices(offered: list[str], key: str) -> list[str]:
        extra = [p[key] for p in saved or [] if p.get(key) and p[key] not in offered]
        return [*offered, *dict.fromkeys(extra)]

    fields: dict[vol.Marker, Any] = {}
    if entry.options.get(CONF_WORK_MODE_ENTITY) and (
        modes := choices(
            work_modes(hass, entry.options.get(CONF_WORK_MODE_ENTITY)), CONF_WORK_MODE
        )
    ):
        fields[vol.Optional(CONF_WORK_MODE)] = _dropdown(modes)
    if speeds := choices(fan_speeds(hass, entry), CONF_FAN_SPEED):
        fields[vol.Optional(CONF_FAN_SPEED)] = _dropdown(speeds)
    return vol.Schema(
        {
            **fields,
            vol.Optional(CONF_START): selector.TimeSelector(),
            vol.Optional(CONF_END): selector.TimeSelector(),
            vol.Required(CONF_FORCED): selector.BooleanSelector(),
            vol.Optional(CONF_GAP_HOURS): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=24,
                    step=0.5,
                    unit_of_measurement="h",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(CONF_DAYS): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=WEEKDAYS, multiple=True, translation_key="weekday"
                )
            ),
        }
    )


def _minutes(value: str | None) -> int | None:
    if not value:
        return None
    hour, minute, *_ = (int(x) for x in str(value).split(":"))
    return hour * 60 + minute


def validate_passes(
    hass: HomeAssistant,
    entry: ConfigEntry,
    raw: Any,
    current: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """The passes to save, and errors keyed "passes" or "passes.<i>.<field>".

    A pass keeps its id if it already belongs to the room, otherwise it gets
    a new one. Windows must follow the order of the list for passes that
    share a day: a pass waits for the earlier ones, so an earlier window
    later in the list would make it miss its deadline.
    """
    if not isinstance(raw, list) or not all(isinstance(p, dict) for p in raw):
        return [], {CONF_PASSES: "invalid"}
    if len(raw) > MAX_PASSES:
        return [], {CONF_PASSES: "too_many_passes"}
    schema = pass_schema(hass, entry, current)
    keys = {str(k) for k in schema.schema}
    known = {p.get(CONF_PASS_ID) for p in current}
    errors: dict[str, str] = {}
    passes: list[dict[str, Any]] = []
    used: set[str] = set()
    for i, item in enumerate(raw):
        try:
            # A field cleared in the form may come as null or "".
            data = schema(
                {k: v for k, v in item.items() if k in keys and v not in (None, "")}
            )
        except vol.Invalid as err:
            for e in err.errors if isinstance(err, vol.MultipleInvalid) else [err]:
                field = str(e.path[0]) if e.path else "base"
                errors[f"{CONF_PASSES}.{i}.{field}"] = "invalid"
            continue
        data = {k: v for k, v in data.items() if v not in (None, "", [])}
        pass_id = item.get(CONF_PASS_ID)
        if pass_id not in known or pass_id in used:
            pass_id = new_pass_id()
        used.add(pass_id)
        start, end = _minutes(data.get(CONF_START)), _minutes(data.get(CONF_END))
        if start is not None and end is not None and start >= end:
            errors[f"{CONF_PASSES}.{i}.{CONF_END}"] = "end_before_start"
        passes.append({CONF_PASS_ID: pass_id, **data})
    if errors:
        return [], errors

    def days(p: dict[str, Any]) -> set[str]:
        return set(p.get(CONF_DAYS) or WEEKDAYS)

    for j, later in enumerate(passes):
        for earlier in passes[:j]:
            if not days(earlier) & days(later):
                continue
            for key in (CONF_START, CONF_END):
                a, b = _minutes(earlier.get(key)), _minutes(later.get(key))
                if a is not None and b is not None and b < a:
                    errors.setdefault(f"{CONF_PASSES}.{j}.{key}", "window_order")
    return ([], errors) if errors else (passes, {})


# --------------------------------------------------------------- settings


def settings_sections(
    hass: HomeAssistant, entry: ConfigEntry, work_mode_entity: str | None
) -> dict[str, vol.Schema]:
    """Fields of the global settings, by section (fan speeds from the robot).

    `work_mode_entity` is the entity chosen in the form, maybe not saved yet:
    the robot section may depend on it.
    """
    sections = {
        SECTION_SCHEDULE: vol.Schema(
            {
                vol.Optional(CONF_QUIET_START): selector.TimeSelector(),
                vol.Optional(CONF_QUIET_END): selector.TimeSelector(),
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

    robot: dict[vol.Marker, Any] = {
        vol.Required(CONF_MIN_BATTERY): selector.NumberSelector(
            selector.NumberSelectorConfig(min=0, max=100, step=5, unit_of_measurement="%")
        )
    }
    if speeds := fan_speeds(hass, entry):
        robot[vol.Optional(CONF_NORMAL_FAN_SPEED)] = _dropdown(speeds)
        robot[vol.Optional(CONF_QUIET_FAN_SPEED)] = _dropdown(speeds)
    robot[vol.Optional(CONF_RESTORE_SETTINGS, default=False)] = (
        selector.BooleanSelector()
    )
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
        CONF_RESTORE_SETTINGS,
    }
