"""Config flow for Tidy Rooms."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
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
from homeassistant.helpers import selector

from .const import (
    CONF_AREA,
    CONF_JOB_DONE_DELAY,
    CONF_MIN_BATTERY,
    CONF_QUIET_END,
    CONF_QUIET_START,
    CONF_START_TIMEOUT,
    CONF_VACUUM,
    CONF_WAKE_DAYS,
    CONF_WAKE_MINUTES,
    CONF_WAKE_SENSORS,
    CONF_WORK_MODE_ENTITY,
    DEFAULT_JOB_DONE_DELAY,
    DEFAULT_MIN_BATTERY,
    DEFAULT_QUIET_END,
    DEFAULT_QUIET_START,
    DEFAULT_START_TIMEOUT,
    DEFAULT_WAKE_MINUTES,
    DOMAIN,
    SUBENTRY_ROOM,
)
from .schema import (
    ROOM_DEFAULTS,
    SECTION_ROBOT,
    SECTION_SCHEDULE,
    SECTION_SIGNALS,
    SECTION_WAKE,
    merge_room,
    room_schema,
    room_title,
    settings_sections,
    validate_room,
)


class TidyRoomsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create one entry per robot vacuum."""

    VERSION = 2

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

        sections = settings_sections(self.hass, self.config_entry, None)
        schema = vol.Schema(
            {
                **sections[SECTION_SCHEDULE].schema,
                **sections[SECTION_WAKE].schema,
                **sections[SECTION_SIGNALS].schema,
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

        fields = settings_sections(
            self.hass, self.config_entry, self._data.get(CONF_WORK_MODE_ENTITY)
        )[SECTION_ROBOT].schema
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

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a room."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = validate_room(self._get_entry(), user_input, None)
            if not errors:
                # The program is set in the Tidy Rooms panel: it starts empty.
                return self.async_create_entry(
                    title=room_title(self.hass, user_input),
                    data=merge_room(None, user_input),
                    unique_id=user_input[CONF_AREA],
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                room_schema(), user_input or ROOM_DEFAULTS
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
            errors = validate_room(self._get_entry(), user_input, subentry.subentry_id)
            if not errors:
                return self.async_update_and_abort(
                    self._get_entry(),
                    subentry,
                    title=room_title(self.hass, user_input),
                    data=merge_room(dict(subentry.data), user_input),
                    unique_id=user_input[CONF_AREA],
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                room_schema(), user_input or subentry.data
            ),
            errors=errors,
        )
