"""Runtime engine: feeds the planner with live state and drives the robot."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, time, timedelta
from enum import StrEnum
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.vacuum import (
    ATTR_FAN_SPEED,
    DOMAIN as VACUUM_DOMAIN,
    SERVICE_CLEAN_AREA,
    SERVICE_RETURN_TO_BASE,
    SERVICE_SET_FAN_SPEED,
    VacuumActivity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Context, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.script import Script, async_validate_actions_config
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_AREA,
    CONF_BATTERY_ENTITY,
    CONF_CLEAN_ACTION,
    CONF_EMPTY_MINUTES,
    CONF_FINISHED_EVENT,
    CONF_JOB_ENTITY,
    CONF_FULL_DEADLINE,
    CONF_FULL_MODE_OPTION,
    CONF_FULL_PER_DAY,
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
    DEFAULT_JOB_DONE_DELAY,
    DEFAULT_START_TIMEOUT,
    DOMAIN,
    FAILED_COOLDOWN_MINUTES,
    FINISHED_OK_EVENTS,
    MAX_JOB_DURATION,
    MAX_START_ATTEMPTS,
    STORAGE_VERSION,
    SUBENTRY_ROOM,
    WEEKDAYS,
)
from .planner import (
    CleanKind,
    Decision,
    GlobalConfig,
    Plan,
    RobotState,
    RoomConfig,
    RoomState,
    plan,
    should_interrupt,
)

_LOGGER = logging.getLogger(__name__)

TICK = timedelta(minutes=1)
SAVE_DELAY = 10  # seconds
_BAD = (STATE_UNAVAILABLE, STATE_UNKNOWN)


class JobPhase(StrEnum):
    """Phase of the running job."""

    STARTING = "starting"  # command sent, robot not moving yet
    RUNNING = "running"  # robot cleaning, or back at the dock mid-job
    FINISHING = "finishing"  # docked, waiting to be sure the job is over


@dataclass(slots=True)
class Job:
    """The job the robot is doing for us."""

    decision: Decision
    phase: JobPhase
    started: datetime  # last start attempt
    created: datetime  # first start attempt
    attempts: int = 1
    docked_since: datetime | None = None
    quiet_applied: bool = False


@dataclass(slots=True)
class Room:
    """Configuration and live state of one room."""

    subentry_id: str
    area_id: str
    config: RoomConfig
    state: RoomState
    clean_action: list[dict[str, Any]] | None = None
    script: Script | None = None
    action_error: bool = False
    last_result: str | None = None  # done / interrupted / failed / stopped


def _time(value: str | None) -> time | None:
    return dt_util.parse_time(value) if value else None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _dt(value: str | None) -> datetime | None:
    return dt_util.parse_datetime(value) if value else None


@dataclass(slots=True)
class _Persisted:
    day: str = ""
    awake_day: str = ""
    enabled: bool = True
    rooms: dict[str, dict[str, Any]] = field(default_factory=dict)


class TidyRoomsEngine:
    """Owns the live state of one Tidy Rooms entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Read the configuration."""
        self.hass = hass
        self.entry = entry
        opts = entry.options
        self.vacuum_entity: str = entry.data[CONF_VACUUM]
        self.gcfg = GlobalConfig(
            quiet_start=_time(opts.get(CONF_QUIET_START)),
            quiet_end=_time(opts.get(CONF_QUIET_END)),
            min_battery=int(opts.get(CONF_MIN_BATTERY, 0)),
        )
        self.wake_sensors: list[str] = list(opts.get(CONF_WAKE_SENSORS) or [])
        self.wake_minutes = int(opts.get(CONF_WAKE_MINUTES, 0))
        self.wake_days: list[str] = list(opts.get(CONF_WAKE_DAYS) or [])
        self.work_mode_entity: str | None = opts.get(CONF_WORK_MODE_ENTITY)
        self.mode_option = {
            CleanKind.FULL: opts.get(CONF_FULL_MODE_OPTION),
            CleanKind.VACUUM: opts.get(CONF_VACUUM_MODE_OPTION),
        }
        self.normal_fan: str | None = opts.get(CONF_NORMAL_FAN_SPEED)
        self.quiet_fan: str | None = opts.get(CONF_QUIET_FAN_SPEED)
        self.battery_entity: str | None = opts.get(CONF_BATTERY_ENTITY)
        self.finished_event: str | None = opts.get(CONF_FINISHED_EVENT)
        # Binary sensor that is on for the whole job (preferred end signal).
        self.job_entity: str | None = opts.get(CONF_JOB_ENTITY)
        self.start_timeout = timedelta(
            minutes=int(opts.get(CONF_START_TIMEOUT, DEFAULT_START_TIMEOUT))
        )
        self.done_delay = timedelta(
            minutes=int(opts.get(CONF_JOB_DONE_DELAY, DEFAULT_JOB_DONE_DELAY))
        )

        self.rooms: dict[str, Room] = {}
        for sub in entry.subentries.values():
            if sub.subentry_type != SUBENTRY_ROOM:
                continue
            d = sub.data
            self.rooms[sub.subentry_id] = Room(
                subentry_id=sub.subentry_id,
                area_id=d[CONF_AREA],
                config=RoomConfig(
                    room_id=sub.subentry_id,
                    name=sub.title,
                    occupancy_sensors=tuple(d.get(CONF_OCCUPANCY_SENSORS) or ()),
                    proxy_sensors=tuple(d.get(CONF_PROXY_SENSORS) or ()),
                    empty_minutes=int(d.get(CONF_EMPTY_MINUTES, 0)),
                    full_per_day=int(d.get(CONF_FULL_PER_DAY, 0)),
                    vacuum_per_day=int(d.get(CONF_VACUUM_PER_DAY, 0)),
                    min_gap=timedelta(hours=float(d.get(CONF_MIN_GAP_HOURS, 0))),
                    full_deadline=_time(d.get(CONF_FULL_DEADLINE)),
                    vacuum_deadline=_time(d.get(CONF_VACUUM_DEADLINE)),
                ),
                state=RoomState(),
                clean_action=d.get(CONF_CLEAN_ACTION) or None,
            )

        self.enabled = True
        self.job: Job | None = None
        self.last_plan: Plan = Plan(decision=None)
        self.awake_today = False
        self._awake_day = ""
        self._day = ""
        self._failed_until: datetime | None = None
        self._wake_on_since: dict[str, datetime] = {}
        self._unsubs: list[Callable[[], None]] = []
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._context = Context()

    # ------------------------------------------------------------------ setup

    @property
    def signal(self) -> str:
        """Dispatcher signal sent when anything changes."""
        return f"{DOMAIN}_{self.entry.entry_id}_update"

    async def async_start(self) -> None:
        """Restore state and start listening."""
        await self._async_restore()
        await self._async_build_scripts()
        now = dt_util.now()
        self._roll_day(now)
        for room in self.rooms.values():
            self._refresh_room(room, now, initial=True)
        for sensor in self.wake_sensors:
            state = self.hass.states.get(sensor)
            if state and state.state == STATE_ON:
                self._wake_on_since[sensor] = state.last_changed

        watched = {self.vacuum_entity, *self.wake_sensors}
        for room in self.rooms.values():
            watched.update(room.config.occupancy_sensors, room.config.proxy_sensors)
        if self.finished_event:
            watched.add(self.finished_event)
        if self.job_entity:
            watched.add(self.job_entity)
        self._unsubs.append(
            async_track_state_change_event(self.hass, sorted(watched), self._on_state)
        )
        self._unsubs.append(async_track_time_interval(self.hass, self._on_tick, TICK))
        self._unsubs.append(
            async_track_time_change(self.hass, self._on_midnight, 0, 0, 0)
        )
        self._evaluate()

    async def async_stop(self) -> None:
        """Stop listening and save."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        await self._store.async_save(self._serialize())

    async def _async_build_scripts(self) -> None:
        """Validate the custom clean actions (the selector does not)."""
        for room in self.rooms.values():
            if not room.clean_action:
                continue
            try:
                actions = await async_validate_actions_config(
                    self.hass, cv.SCRIPT_SCHEMA(room.clean_action)
                )
            except (vol.Invalid, HomeAssistantError) as err:
                _LOGGER.error(
                    "Invalid clean action for %s, the room will not be cleaned: %s",
                    room.config.name,
                    err,
                )
                room.action_error = True
                continue
            room.script = Script(
                self.hass,
                actions,
                f"Tidy Rooms {room.config.name}",
                DOMAIN,
                logger=_LOGGER,
            )

    async def _async_restore(self) -> None:
        data = await self._store.async_load() or {}
        self.enabled = data.get("enabled", True)
        self._day = data.get("day", "")
        self._awake_day = data.get("awake_day", "")
        stored = data.get("rooms", {})
        for room_id, room in self.rooms.items():
            saved = stored.get(room_id, {})
            st = room.state
            st.enabled = saved.get("enabled", True)
            st.full_today = saved.get("full_today", 0)
            st.vacuum_today = saved.get("vacuum_today", 0)
            st.last_full = _dt(saved.get("last_full"))
            st.last_vacuum = _dt(saved.get("last_vacuum"))
            room.last_result = saved.get("last_result")

    def _serialize(self) -> dict[str, Any]:
        return {
            "day": self._day,
            "awake_day": self._awake_day,
            "enabled": self.enabled,
            "rooms": {
                room_id: {
                    "enabled": r.state.enabled,
                    "full_today": r.state.full_today,
                    "vacuum_today": r.state.vacuum_today,
                    "last_full": _iso(r.state.last_full),
                    "last_vacuum": _iso(r.state.last_vacuum),
                    "last_result": r.last_result,
                }
                for room_id, r in self.rooms.items()
            },
        }

    def _save(self) -> None:
        self._store.async_delay_save(self._serialize, SAVE_DELAY)

    # ------------------------------------------------------------- live state

    def _roll_day(self, now: datetime) -> None:
        today = now.date().isoformat()
        if self._day != today:
            self._day = today
            for room in self.rooms.values():
                room.state.full_today = 0
                room.state.vacuum_today = 0
            self._save()
        self.awake_today = self._awake_day == today

    def _refresh_room(self, room: Room, now: datetime, initial: bool = False) -> None:
        st, cfg = room.state, room.config
        if cfg.occupancy_sensors:
            states = [self.hass.states.get(e) for e in cfg.occupancy_sensors]
            valid = [s for s in states if s is not None and s.state not in _BAD]
            if not valid:
                st.occupied, st.empty_since = None, None
            elif any(s.state == STATE_ON for s in valid):
                st.occupied, st.empty_since = True, None
            else:
                was_empty = st.occupied is False and st.empty_since is not None
                st.occupied = False
                if initial:
                    st.empty_since = max(s.last_changed for s in valid)
                elif not was_empty:
                    st.empty_since = now
        st.proxy_active = any(
            (s := self.hass.states.get(e)) is not None and s.state == STATE_ON
            for e in cfg.proxy_sensors
        )

    def _update_awake(self, now: datetime) -> None:
        if self.awake_today:
            return
        if not self.wake_sensors or WEEKDAYS[now.weekday()] not in self.wake_days:
            return
        if self.gcfg.quiet_end is not None and now.time() < self.gcfg.quiet_end:
            return
        need = timedelta(minutes=self.wake_minutes)
        for since in self._wake_on_since.values():
            # Presence that started during quiet hours counts from their end.
            if self.gcfg.quiet_end is not None:
                since = max(
                    since, datetime.combine(now.date(), self.gcfg.quiet_end, now.tzinfo)
                )
            if now - since >= need:
                self.awake_today = True
                self._awake_day = now.date().isoformat()
                self._save()
                return

    @property
    def awake(self) -> bool:
        """False while waiting for the household to wake up."""
        now = dt_util.now()
        if not self.wake_sensors or WEEKDAYS[now.weekday()] not in self.wake_days:
            return True
        return self.awake_today

    def _robot(self) -> RobotState:
        state = self.hass.states.get(self.vacuum_entity)
        if state is None or state.state in _BAD:
            return RobotState(available=False, idle=False)
        battery: int | None = None
        if self.battery_entity:
            bat = self.hass.states.get(self.battery_entity)
            if bat is not None and bat.state not in _BAD:
                try:
                    battery = int(float(bat.state))
                except ValueError:
                    battery = None
        elif (level := state.attributes.get("battery_level")) is not None:
            battery = int(level)
        idle = state.state in (VacuumActivity.DOCKED, VacuumActivity.IDLE)
        if self.job_entity:
            job_state = self.hass.states.get(self.job_entity)
            # A job started elsewhere (app, schedule) keeps the robot busy.
            if job_state is not None and job_state.state == STATE_ON:
                idle = False
        return RobotState(available=True, idle=idle, battery=battery)

    # ---------------------------------------------------------------- events

    @callback
    def _on_state(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        new = event.data["new_state"]
        now = dt_util.now()
        if entity_id in self.wake_sensors:
            if new is not None and new.state == STATE_ON:
                self._wake_on_since.setdefault(entity_id, now)
            else:
                self._wake_on_since.pop(entity_id, None)
        if entity_id == self.finished_event and new is not None and self.job:
            self._on_finished_event(new.attributes.get("event_type"), now)
        if entity_id == self.job_entity and new is not None:
            self._on_job_entity(new.state, now)
        if entity_id == self.vacuum_entity:
            self._on_vacuum(new.state if new else None, now)
        for room in self.rooms.values():
            cfg = room.config
            if entity_id in cfg.occupancy_sensors or entity_id in cfg.proxy_sensors:
                self._refresh_room(room, now)
                self._check_interrupt(room)
        self._evaluate()

    @callback
    def _on_tick(self, now: datetime) -> None:
        now = dt_util.now()
        self._roll_day(now)
        self._check_job_timers(now)
        self._evaluate()

    @callback
    def _on_midnight(self, now: datetime) -> None:
        self._roll_day(dt_util.now())
        self._evaluate()

    # ------------------------------------------------------------------ jobs

    def _on_vacuum(self, state: str | None, now: datetime) -> None:
        job = self.job
        if job is None or state is None or state in _BAD:
            return  # unavailable/unknown say nothing about the job
        if state in (VacuumActivity.CLEANING, VacuumActivity.RETURNING):
            job.phase = JobPhase.RUNNING
            job.docked_since = None
        elif state in (VacuumActivity.DOCKED, VacuumActivity.IDLE):
            if self.job_entity:
                return  # the job entity decides when the job is over
            if job.phase is not JobPhase.STARTING and job.docked_since is None:
                job.phase = JobPhase.FINISHING
                job.docked_since = now
        elif state == VacuumActivity.ERROR:
            self._end_job("failed")

    def _on_job_entity(self, state: str, now: datetime) -> None:
        job = self.job
        if job is None or state in _BAD:
            return
        if state == STATE_ON:
            job.phase = JobPhase.RUNNING
            job.docked_since = None
        elif job.phase is not JobPhase.STARTING:
            # On, then off: the robot reports the job as finished.
            self._complete_job(now)

    def _on_finished_event(self, event_type: str | None, now: datetime) -> None:
        job = self.job
        if job is None or job.phase is JobPhase.STARTING:
            return
        if event_type in FINISHED_OK_EVENTS:
            self._complete_job(now)
        elif event_type is not None:
            self._end_job("stopped")

    def _check_job_timers(self, now: datetime) -> None:
        job = self.job
        if job is None:
            return
        if now - job.created >= MAX_JOB_DURATION:
            _LOGGER.warning(
                "Job in %s did not end within %s: giving up",
                self.rooms[job.decision.room_id].config.name,
                MAX_JOB_DURATION,
            )
            self._end_job("failed")
            return
        if job.phase is JobPhase.STARTING and now - job.started >= self.start_timeout:
            if job.attempts >= MAX_START_ATTEMPTS:
                _LOGGER.warning(
                    "Robot did not start cleaning %s after %s attempts",
                    self.rooms[job.decision.room_id].config.name,
                    job.attempts,
                )
                self._failed_until = now + timedelta(minutes=FAILED_COOLDOWN_MINUTES)
                self._end_job("failed")
                return
            job.attempts += 1
            job.started = now
            self.hass.async_create_task(self._async_send_job(job.decision))
        elif (
            job.phase is JobPhase.FINISHING
            and job.docked_since is not None
            and now - job.docked_since >= self.done_delay
        ):
            self._complete_job(now)

    def _complete_job(self, now: datetime) -> None:
        job = self.job
        if job is None:
            return
        room = self.rooms[job.decision.room_id]
        st = room.state
        if job.decision.kind is CleanKind.FULL:
            st.full_today += 1
            st.last_full = now
        st.vacuum_today += 1
        st.last_vacuum = now
        self._end_job("done")

    def _end_job(self, result: str) -> None:
        job = self.job
        if job is None:
            return
        self.rooms[job.decision.room_id].last_result = result
        self.job = None
        self._save()
        self._notify()

    def _check_interrupt(self, room: Room) -> None:
        job = self.job
        if job is None or job.decision.room_id != room.subentry_id:
            return
        if should_interrupt(room.config, room.state, job.decision):
            _LOGGER.info("Someone entered %s: sending the robot home", room.config.name)
            self._end_job("interrupted")
            self.hass.async_create_task(self._async_return_home())
        elif (
            job.decision.forced
            and not job.quiet_applied
            and room.state.occupied is not False
            and self.quiet_fan
        ):
            job.quiet_applied = True
            self.hass.async_create_task(self._async_fan(self.quiet_fan))

    # -------------------------------------------------------------- planning

    @callback
    def _evaluate(self) -> None:
        now = dt_util.now()
        self._update_awake(now)
        robot = self._robot()
        active = self.job.decision.room_id if self.job else None
        if self._failed_until and now < self._failed_until:
            robot = RobotState(available=False, idle=False)
        result = plan(
            now,
            self.gcfg,
            [
                (r.config, replace(r.state, enabled=False) if r.action_error else r.state)
                for r in self.rooms.values()
            ],
            robot,
            awake=self.awake,
            active_room=active,
        )
        self.last_plan = result
        if self.enabled and self.job is None and result.decision is not None:
            self._start_job(result.decision, now)
        self._notify()

    def _start_job(self, decision: Decision, now: datetime) -> None:
        self.job = Job(
            decision=decision, phase=JobPhase.STARTING, started=now, created=now
        )
        self.job.quiet_applied = decision.quiet
        _LOGGER.info(
            "Cleaning %s (%s%s)",
            self.rooms[decision.room_id].config.name,
            decision.kind,
            ", forced" if decision.forced else "",
        )
        self.hass.async_create_task(self._async_send_job(decision))

    async def async_clean_now(self, room_id: str, kind: CleanKind | None = None) -> None:
        """Clean a room right away, ignoring occupancy and targets."""
        if self.job is not None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="robot_busy")
        room = self.rooms[room_id]
        if kind is None:
            kind = (
                CleanKind.FULL
                if room.state.full_today < room.config.full_per_day
                else CleanKind.VACUUM
            )
        # Forced: someone asked for it, so presence must not interrupt it.
        self._start_job(Decision(room_id, kind, forced=True, quiet=False), dt_util.now())
        self._notify()

    async def async_set_enabled(self, enabled: bool) -> None:
        """Pause or resume automatic cleaning."""
        self.enabled = enabled
        self._save()
        self._evaluate()

    async def async_set_room_enabled(self, room_id: str, enabled: bool) -> None:
        """Pause or resume a room."""
        self.rooms[room_id].state.enabled = enabled
        self._save()
        self._evaluate()

    # ---------------------------------------------------------- robot calls

    async def _async_call(self, domain: str, service: str, data: dict[str, Any]) -> None:
        try:
            await self.hass.services.async_call(
                domain, service, data, blocking=True, context=self._context
            )
        except HomeAssistantError as err:
            _LOGGER.warning("%s.%s failed: %s", domain, service, err)

    async def _async_fan(self, speed: str) -> None:
        await self._async_call(
            VACUUM_DOMAIN,
            SERVICE_SET_FAN_SPEED,
            {ATTR_ENTITY_ID: self.vacuum_entity, ATTR_FAN_SPEED: speed},
        )

    async def _async_return_home(self) -> None:
        await self._async_call(
            VACUUM_DOMAIN, SERVICE_RETURN_TO_BASE, {ATTR_ENTITY_ID: self.vacuum_entity}
        )

    async def _async_send_job(self, decision: Decision) -> None:
        room = self.rooms[decision.room_id]
        if self.work_mode_entity and (option := self.mode_option[decision.kind]):
            await self._async_call(
                "select",
                "select_option",
                {ATTR_ENTITY_ID: self.work_mode_entity, "option": option},
            )
        speed = self.quiet_fan if decision.quiet else self.normal_fan
        if speed:
            await self._async_fan(speed)
        if room.script is not None:
            try:
                await room.script.async_run(
                    run_variables={
                        "room": room.config.name,
                        "area_id": room.area_id,
                        "kind": str(decision.kind),
                        "quiet": decision.quiet,
                        "vacuum_entity": self.vacuum_entity,
                    },
                    context=self._context,
                )
            except HomeAssistantError as err:
                _LOGGER.warning("Clean action for %s failed: %s", room.config.name, err)
            return
        await self._async_call(
            VACUUM_DOMAIN,
            SERVICE_CLEAN_AREA,
            {ATTR_ENTITY_ID: self.vacuum_entity, "cleaning_area_id": [room.area_id]},
        )

    # ---------------------------------------------------------------- output

    def _notify(self) -> None:
        async_dispatcher_send(self.hass, self.signal)
