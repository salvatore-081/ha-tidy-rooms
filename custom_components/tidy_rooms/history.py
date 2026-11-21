"""Log of the jobs, kept for the panel."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN

HISTORY_DAYS = 30
HISTORY_VERSION = 1
SAVE_DELAY = 10  # seconds


@dataclass(frozen=True, slots=True)
class JobRecord:
    """One job, from the first start command to its end."""

    room_id: str
    room: str  # name at the time, the room may be deleted later
    forced: bool  # deadline passed (or started by hand)
    quiet: bool  # quiet fan speed used
    manual: bool  # started from a button or the panel
    attempts: int
    started: str  # ISO
    ended: str  # ISO
    result: str  # done / interrupted / failed / stopped
    work_mode: str | None = None  # None: the robot's mode was left as it was
    pass_id: str | None = None  # None: a manual cleaning that did not count
    kind: str | None = None  # full / vacuum: jobs logged by 0.3.0


_FIELDS = {f.name for f in fields(JobRecord)}


class JobHistory:
    """The last HISTORY_DAYS of jobs of one entry, oldest first."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize."""
        self._store: Store[dict[str, Any]] = Store(
            hass, HISTORY_VERSION, f"{DOMAIN}.{entry_id}.history"
        )
        self.records: list[JobRecord] = []

    async def async_load(self) -> None:
        """Read the log."""
        data = await self._store.async_load() or {}
        self.records = []
        for raw in data.get("jobs", []):
            try:
                known = {k: v for k, v in raw.items() if k in _FIELDS}
                self.records.append(JobRecord(**known))
            except TypeError:
                continue  # unusable: skip
        self._prune(dt_util.now())

    def add(self, record: JobRecord) -> None:
        """Append a job and save soon."""
        self.records.append(record)
        self._prune(dt_util.now())
        self._store.async_delay_save(self._data, SAVE_DELAY)

    async def async_save(self) -> None:
        """Save now."""
        await self._store.async_save(self._data())

    async def async_remove(self) -> None:
        """Delete the log (entry removed)."""
        await self._store.async_remove()

    def query(
        self, now: datetime, days: int, room_id: str | None = None
    ) -> list[JobRecord]:
        """Jobs started in the last `days` days, newest first."""
        since = now - timedelta(days=days)
        return [
            r
            for r in reversed(self.records)
            if (room_id is None or r.room_id == room_id)
            and (started := dt_util.parse_datetime(r.started)) is not None
            and started >= since
        ]

    def _prune(self, now: datetime) -> None:
        since = now - timedelta(days=HISTORY_DAYS)
        self.records = [
            r
            for r in self.records
            if (started := dt_util.parse_datetime(r.started)) is not None
            and started >= since
        ]

    def _data(self) -> dict[str, Any]:
        return {"jobs": [asdict(r) for r in self.records]}
