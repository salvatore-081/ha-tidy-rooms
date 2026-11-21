"""Config flow for Tidy Rooms."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.components.event import DOMAIN as EVENT_DOMAIN
from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.vacuum import DOMAIN as VACUUM_DOMAIN
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers import area_registry as ar, selector

from .const import (
    CONF_AREA,
    CONF_BATTERY_ENTITY,
    CONF_CLEAN_ACTION,
    CONF_EMPTY_MINUTES,
    CONF_FINISHED_EVENT,
    CONF_FULL_DEADLINE,
    CONF_FULL_MODE_OPTION,
    CONF_FULL_PER_DAY,
    CONF_JOB_ENTITY,
    CONF_JOB_DONE_DELAY,
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
    DEFAULT_JOB_DONE_DELAY,
    DEFAULT_MIN_BATTERY,
    DEFAULT_MIN_GAP_HOURS,
    DEFAULT_QUIET_END,
    DEFAULT_QUIET_START,
    DEFAULT_START_TIMEOUT,
    DEFAULT_VACUUM_DEADLINE,
    DEFAULT_VACUUM_PER_DAY,
    DEFAULT_WAKE_MINUTES,
    DOMAIN,
    SUBENTRY_ROOM,
    WEEKDAYS,
)

OCCUPANCY_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=BINARY_SENSOR_DOMAIN, multiple=True)
)


def _minutes(max_value: int) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
            max=max_value,
            step=1,
            unit_of_measurement="min",
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _count(max_value: int) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0, max=max_value, step=1, mode=selector.NumberSelectorMode.BOX
        )
    )


class TidyRoomsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create one entry per robot vacuum."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the robot vacuum."""
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_VACUUM])
            self._abort_if_unique_id_configured()
            state = self.hass.states.get(user_input[CONF_VACUUM])
            title = state.name if state else user_input[CONF_VACUUM]
            return self.async_create_entry(
                title=title,
                data={CONF_VACUUM: user_input[CONF_VACUUM]},
                options={
                    CONF_QUIET_START: DEFAULT_QUIET_START,
                    CONF_QUIET_END: DEFAULT_QUIET_END,
                    CONF_MIN_BATTERY: DEFAULT_MIN_BATTERY,
                    CONF_WAKE_SENSORS: [],
                    CONF_WAKE_MINUTES: DEFAULT_WAKE_MINUTES,
                    CONF_WAKE_DAYS: ["sat", "sun"],
                    CONF_START_TIMEOUT: DEFAULT_START_TIMEOUT,
                    CONF_JOB_DONE_DELAY: DEFAULT_JOB_DONE_DELAY,
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_VACUUM): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=VACUUM_DOMAIN)
                    )
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> TidyRoomsOptionsFlow:
        """Global settings."""
        return TidyRoomsOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Rooms are subentries."""
        return {SUBENTRY_ROOM: RoomSubentryFlow}


class TidyRoomsOptionsFlow(OptionsFlow):
    """Global settings, in two steps: schedule, then how to drive the robot."""

    def __init__(self) -> None:
        """Initialize."""
        self._data: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Schedule and general settings."""
        if user_input is not None:
            self._data = dict(user_input)
            return await self.async_step_robot()

        schema = vol.Schema(
            {
                vol.Optional(CONF_QUIET_START): selector.TimeSelector(),
                vol.Optional(CONF_QUIET_END): selector.TimeSelector(),
                vol.Optional(CONF_WAKE_SENSORS): OCCUPANCY_SELECTOR,
                vol.Required(CONF_WAKE_MINUTES): _minutes(240),
                vol.Optional(CONF_WAKE_DAYS): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=WEEKDAYS,
                        multiple=True,
                        translation_key="weekday",
                    )
                ),
                vol.Required(CONF_MIN_BATTERY): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=100, step=5, unit_of_measurement="%"
                    )
                ),
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
                vol.Required(CONF_START_TIMEOUT): _minutes(30),
                vol.Required(CONF_JOB_DONE_DELAY): _minutes(30),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema, self.config_entry.options
            ),
        )

    async def async_step_robot(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Work modes and fan speeds, offered from the robot's own lists."""
        if user_input is not None:
            return self.async_create_entry(data={**self._data, **user_input})

        fields: dict[vol.Marker, Any] = {}
        vacuum = self.hass.states.get(self.config_entry.data[CONF_VACUUM])
        fan_speeds = list(vacuum.attributes.get("fan_speed_list") or []) if vacuum else []
        if fan_speeds:
            fan = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=fan_speeds, mode=selector.SelectSelectorMode.DROPDOWN
                )
            )
            fields[vol.Optional(CONF_NORMAL_FAN_SPEED)] = fan
            fields[vol.Optional(CONF_QUIET_FAN_SPEED)] = fan

        if work_mode := self._data.get(CONF_WORK_MODE_ENTITY):
            mode_state = self.hass.states.get(work_mode)
            modes = list(mode_state.attributes.get("options") or []) if mode_state else []
            if modes:
                mode = selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=modes, mode=selector.SelectSelectorMode.DROPDOWN
                    )
                )
                fields[vol.Optional(CONF_FULL_MODE_OPTION)] = mode
                fields[vol.Optional(CONF_VACUUM_MODE_OPTION)] = mode

        if not fields:
            return self.async_create_entry(data=self._data)

        return self.async_show_form(
            step_id="robot",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(fields), self.config_entry.options
            ),
        )


class RoomSubentryFlow(ConfigSubentryFlow):
    """Add or edit a room."""

    def _schema(self) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(CONF_AREA): selector.AreaSelector(),
                vol.Optional(CONF_OCCUPANCY_SENSORS): OCCUPANCY_SELECTOR,
                vol.Optional(CONF_PROXY_SENSORS): OCCUPANCY_SELECTOR,
                vol.Required(CONF_EMPTY_MINUTES): _minutes(240),
                vol.Required(CONF_FULL_PER_DAY): _count(3),
                vol.Required(CONF_VACUUM_PER_DAY): _count(6),
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

    def _title(self, data: dict[str, Any]) -> str:
        area = ar.async_get(self.hass).async_get_area(data[CONF_AREA])
        return area.name if area else data[CONF_AREA]

    def _validate(self, data: dict[str, Any], current: str | None) -> dict[str, str]:
        errors: dict[str, str] = {}
        for sub in self._get_entry().subentries.values():
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

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a room."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._validate(user_input, None)
            if not errors:
                return self.async_create_entry(
                    title=self._title(user_input),
                    data=user_input,
                    unique_id=user_input[CONF_AREA],
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                self._schema(),
                user_input
                or {
                    CONF_EMPTY_MINUTES: DEFAULT_EMPTY_MINUTES,
                    CONF_FULL_PER_DAY: DEFAULT_FULL_PER_DAY,
                    CONF_VACUUM_PER_DAY: DEFAULT_VACUUM_PER_DAY,
                    CONF_MIN_GAP_HOURS: DEFAULT_MIN_GAP_HOURS,
                    CONF_FULL_DEADLINE: DEFAULT_FULL_DEADLINE,
                    CONF_VACUUM_DEADLINE: DEFAULT_VACUUM_DEADLINE,
                },
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Edit a room."""
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._validate(user_input, subentry.subentry_id)
            if not errors:
                return self.async_update_and_abort(
                    self._get_entry(),
                    subentry,
                    title=self._title(user_input),
                    data=user_input,
                    unique_id=user_input[CONF_AREA],
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                self._schema(), user_input or subentry.data
            ),
            errors=errors,
        )
