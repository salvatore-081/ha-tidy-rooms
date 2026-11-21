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
CONF_CLEAN_ACTION: Final = "clean_action"

# Cleaning program of a room: a list of passes
CONF_PASSES: Final = "passes"
CONF_PASS_ID: Final = "id"
CONF_WORK_MODE: Final = "work_mode"
CONF_FAN_SPEED: Final = "fan_speed"
CONF_START: Final = "start"
CONF_END: Final = "end"
CONF_FORCED: Final = "forced"
CONF_GAP_HOURS: Final = "gap_hours"
CONF_DAYS: Final = "days"
MAX_PASSES: Final = 6

# Keys of Tidy Rooms 0.3.0, read only by the migration (legacy.py)
CONF_FULL_MODE_OPTION: Final = "full_mode_option"
CONF_VACUUM_MODE_OPTION: Final = "vacuum_mode_option"
CONF_FULL_PER_DAY: Final = "full_per_day"
CONF_VACUUM_PER_DAY: Final = "vacuum_per_day"
CONF_MIN_GAP_HOURS: Final = "min_gap_hours"
CONF_FULL_DEADLINE: Final = "full_deadline"
CONF_VACUUM_DEADLINE: Final = "vacuum_deadline"
CONF_ROOM_FAN_SPEED: Final = "fan_speed"
CONF_ROOM_FULL_MODE: Final = "full_mode"
CONF_ROOM_VACUUM_MODE: Final = "vacuum_mode"

DEFAULT_QUIET_START: Final = "22:30:00"
DEFAULT_QUIET_END: Final = "08:00:00"
DEFAULT_MIN_BATTERY: Final = 30
DEFAULT_WAKE_MINUTES: Final = 15
DEFAULT_START_TIMEOUT: Final = 3  # minutes before retrying a start
DEFAULT_JOB_DONE_DELAY: Final = 5  # minutes docked before a job counts as done
DEFAULT_EMPTY_MINUTES: Final = 10

WEEKDAYS: Final = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

STORAGE_VERSION: Final = 1

# Event types of a "job finished" event entity that mean the job is done.
FINISHED_OK_EVENTS: Final = {"finished", "finished_with_warnings"}
MAX_START_ATTEMPTS: Final = 3
# A job (paused, stuck, never docking) is abandoned after this long.
MAX_JOB_DURATION: Final = timedelta(hours=3)
FAILED_COOLDOWN_MINUTES: Final = 15
