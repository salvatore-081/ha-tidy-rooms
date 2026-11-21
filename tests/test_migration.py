"""Migration of config entries saved by Tidy Rooms 0.3.0 (version 1)."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntryState, ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tidy_rooms.const import DOMAIN, SUBENTRY_ROOM

VACUUM = "vacuum.robot"
MODE = "select.robot_work_mode"

OLD_OPTIONS = {
    "quiet_start": "22:30:00",
    "quiet_end": "08:00:00",
    "min_battery": 30,
    "work_mode_entity": MODE,
    "full_mode_option": "mop_after_vacuum",
    "vacuum_mode_option": "vacuum",
    "normal_fan_speed": "normal",
}
OLD_ROOM = {
    "occupancy_sensors": ["binary_sensor.presence"],
    "empty_minutes": 10,
    "full_per_day": 1,
    "vacuum_per_day": 2,
    "min_gap_hours": 6,
    "full_deadline": "19:00:00",
    "vacuum_deadline": "21:30:00",
}


async def _setup(
    hass: HomeAssistant,
    rooms: list[dict[str, Any]],
    options: dict[str, Any] | None = None,
    version: int = 1,
) -> MockConfigEntry:
    hass.states.async_set(VACUUM, "docked", {"fan_speed_list": ["quiet", "normal"]})
    hass.states.async_set(MODE, "vacuum", {"options": ["vacuum", "mop_after_vacuum"]})
    areas = ar.async_get(hass)
    subentries = []
    for i, data in enumerate(rooms):
        area = areas.async_create(f"Room {i}")
        subentries.append(
            ConfigSubentryData(
                subentry_type=SUBENTRY_ROOM,
                title=area.name,
                unique_id=area.id,
                subentry_id=f"room{i}",
                data={"area": area.id, **data},
            )
        )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Robot",
        version=version,
        data={"vacuum": VACUUM},
        options=OLD_OPTIONS if options is None else options,
        subentries_data=subentries,
    )
    entry.add_to_hass(hass)
    return entry


async def _load(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_default_room(hass: HomeAssistant) -> None:
    entry = await _setup(hass, [OLD_ROOM])
    registry = er.async_get(hass)
    old = {
        key: registry.async_get_or_create(
            domain, DOMAIN, f"room0_{key}", config_entry=entry
        ).entity_id
        for domain, key in [
            ("button", "clean_now_full"),
            ("button", "clean_now_vacuum"),
            ("sensor", "last_full"),
            ("sensor", "last_vacuum"),
        ]
    }
    kept = registry.async_get_or_create(
        "sensor", DOMAIN, "room0_status", config_entry=entry
    ).entity_id

    await _load(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert entry.version == 2
    data = entry.subentries["room0"].data
    assert data["passes"] == [
        {
            "id": "full-1",
            "forced": True,
            "work_mode": "mop_after_vacuum",
            "end": "19:00:00",
        },
        {
            "id": "vacuum-1",
            "forced": True,
            "work_mode": "vacuum",
            "end": "21:30:00",
            "gap_hours": 6.0,
        },
    ]
    assert set(data) == {"area", "occupancy_sensors", "empty_minutes", "passes"}
    assert "full_mode_option" not in entry.options
    assert "vacuum_mode_option" not in entry.options
    assert entry.options["normal_fan_speed"] == "normal"  # untouched
    for entity_id in old.values():
        assert registry.async_get(entity_id) is None
    assert registry.async_get(kept) is not None


async def test_room_settings_and_no_work_mode_entity(hass: HomeAssistant) -> None:
    options = {k: v for k, v in OLD_OPTIONS.items() if not k.endswith("mode_option")}
    options.pop("work_mode_entity")
    entry = await _setup(
        hass,
        [
            {
                **OLD_ROOM,
                "full_per_day": 0,
                "fan_speed": "quiet",
                "vacuum_mode": "vacuum",
            },
            {**OLD_ROOM, "full_deadline": None, "vacuum_per_day": 1, "full_mode": ""},
        ],
        options,
    )
    await _load(hass, entry)
    assert entry.subentries["room0"].data["passes"] == [
        {
            "id": f"vacuum-{n}",
            "forced": True,
            "work_mode": "vacuum",
            "fan_speed": "quiet",
            "end": "21:30:00",
            "gap_hours": 6.0,
        }
        for n in (1, 2)
    ]
    assert entry.subentries["room1"].data["passes"] == [
        {"id": "full-1", "forced": True}
    ]
    assert "fan_speed" not in entry.subentries["room0"].data


async def test_rooms_already_migrated_are_left_alone(hass: HomeAssistant) -> None:
    """An interrupted migration runs again without touching finished rooms."""
    program = [{"id": "abcd1234", "forced": False, "work_mode": "vacuum"}]
    entry = await _setup(hass, [{"empty_minutes": 5, "passes": program}, OLD_ROOM])
    await _load(hass, entry)
    assert entry.subentries["room0"].data["passes"] == program
    assert len(entry.subentries["room1"].data["passes"]) == 2


async def test_newer_version_is_refused(hass: HomeAssistant) -> None:
    entry = await _setup(hass, [], {}, version=3)
    await _load(hass, entry)
    assert entry.state is ConfigEntryState.MIGRATION_ERROR
