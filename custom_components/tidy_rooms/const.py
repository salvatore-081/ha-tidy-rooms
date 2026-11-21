"""Constants for Tidy Rooms."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "tidy_rooms"

SUBENTRY_ROOM: Final = "room"

# Main entry
CONF_VACUUM: Final = "vacuum"

# Options (global settings)
CONF_QUIET_START: Final = "quiet_start"
CONF_QUIET_END: Final = "quiet_end"
CONF_MIN_BATTERY: Final = "min_battery"
CONF_WAKE_SENSORS: Final = "wake_sensors"
CONF_WAKE_MINUTES: Final = "wake_minutes"
CONF_WAKE_DAYS: Final = "wake_days"
CONF_WORK_MODE_ENTITY: Final = "work_mode_entity"
CONF_FULL_MODE_OPTION: Final = "full_mode_option"
CONF_VACUUM_MODE_OPTION: Final = "vacuum_mode_option"
CONF_NORMAL_FAN_SPEED: Final = "normal_fan_speed"
CONF_QUIET_FAN_SPEED: Final = "quiet_fan_speed"
CONF_START_TIMEOUT: Final = "start_timeout"
CONF_JOB_DONE_DELAY: Final = "job_done_delay"
CONF_BATTERY_ENTITY: Final = "battery_entity"
CONF_FINISHED_EVENT: Final = "finished_event"
CONF_JOB_ENTITY: Final = "job_entity"
# Room priority, as a list of subentry ids (set from the panel)
CONF_ROOM_ORDER: Final = "room_order"

# Room subentry
CONF_AREA: Final = "area"
CONF_OCCUPANCY_SENSORS: Final = "occupancy_sensors"
CONF_PROXY_SENSORS: Final = "proxy_sensors"
CONF_EMPTY_MINUTES: Final = "empty_minutes"
CONF_FULL_PER_DAY: Final = "full_per_day"
CONF_VACUUM_PER_DAY: Final = "vacuum_per_day"
CONF_MIN_GAP_HOURS: Final = "min_gap_hours"
CONF_FULL_DEADLINE: Final = "full_deadline"
CONF_VACUUM_DEADLINE: Final = "vacuum_deadline"
CONF_CLEAN_ACTION: Final = "clean_action"

DEFAULT_QUIET_START: Final = "22:30:00"
DEFAULT_QUIET_END: Final = "08:00:00"
DEFAULT_MIN_BATTERY: Final = 30
DEFAULT_WAKE_MINUTES: Final = 15
DEFAULT_START_TIMEOUT: Final = 3  # minutes before retrying a start
DEFAULT_JOB_DONE_DELAY: Final = 5  # minutes docked before a job counts as done
DEFAULT_EMPTY_MINUTES: Final = 10
DEFAULT_FULL_PER_DAY: Final = 1
DEFAULT_VACUUM_PER_DAY: Final = 2
DEFAULT_MIN_GAP_HOURS: Final = 6
DEFAULT_FULL_DEADLINE: Final = "19:00:00"
DEFAULT_VACUUM_DEADLINE: Final = "21:30:00"

WEEKDAYS: Final = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

STORAGE_VERSION: Final = 1

# Event types of a "job finished" event entity that mean the job is done.
FINISHED_OK_EVENTS: Final = {"finished", "finished_with_warnings"}
MAX_START_ATTEMPTS: Final = 3
# A job (paused, stuck, never docking) is abandoned after this long.
MAX_JOB_DURATION: Final = timedelta(hours=3)
FAILED_COOLDOWN_MINUTES: Final = 15
