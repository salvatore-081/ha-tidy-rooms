# Tidy Rooms

A Home Assistant integration that cleans each room **when nobody is in it**, while making sure every room still gets its daily cleaning.

Instead of fixed schedules, you set targets per room (for example *one vacuum and mop pass and two vacuum passes a day, at least 6 hours apart*). Tidy Rooms watches your presence sensors and sends the robot to a room as soon as it has been empty for a while. If a room never empties, it is cleaned anyway after a deadline you choose, with the quiet fan speed.

> **Status: early development.** The rules and the integration are covered by automated tests, but they have not yet driven a robot in a real home. Feedback and issues are welcome.

## How it works

- **One room at a time.** The robot gets a single room per job, so the plan can change between rooms.
- **Daily targets per room**: vacuum and mop passes, vacuum passes (a vacuum and mop pass counts as one), and the minimum gap between two passes.
- **Empty rooms only**: a room is cleaned after its presence sensors have reported nobody for the configured minutes. Rooms without a sensor can use the sensors of other rooms instead ("free while someone is detected elsewhere"), or have no condition at all.
- **Someone walks in**: the robot is sent back to the dock and the room stays due.
- **Deadlines**: after the deadline the room is cleaned even if occupied, with the quiet fan speed, and the job is not interrupted.
- **Quiet hours**: no cleaning at night, not even after a deadline.
- **Wake-up check** (optional): on the days you choose (weekends, by default), cleaning starts only after someone has been detected for a while by the wake-up sensors, for example in the kitchen at breakfast.
- **Robots that do not answer**: if the robot does not start within a few minutes, the command is sent again; after three attempts Tidy Rooms waits 15 minutes.
- **When a job is over**: best with a *cleaning job sensor*, a binary sensor of the robot that stays on for the whole job, also while the robot is back at the dock to empty the dustbin, wash the mop or recharge (for example the *Cleaning job* sensor of the patched Ecovacs integration for the T90 PRO OMNI). Without it, a job counts as done when the robot stays docked for a configurable time, which also treats a return to recharge as the end; a "job finished" event entity, if the robot has one, ends it right away.

Priority when several rooms are due: forced (past the deadline) first, then vacuum and mop passes, then the room that has waited longest.

## Requirements

- Home Assistant 2026.10 or later.
- A robot vacuum entity that supports **area cleaning** (`vacuum.clean_area`), with the robot's rooms mapped to Home Assistant areas: open the vacuum entity settings and map each room to an area. If your robot's integration does not support area cleaning, you can use a custom clean action per room (see below).
- Presence sensors (mmWave sensors work best: they see people sitting still).

## Panel

Tidy Rooms adds a **Tidy Rooms** panel to the sidebar (administrators only), in English, Italian, German, Spanish and French:

- **Overview**: the robot (state, battery, automatic cleaning on or off, the job in progress, the next room), then a tile per room with its status, why it is waiting (for example *empty for 4 of 10 min*, *next pass from 15:20*), today's passes against the targets, the last pass and an estimate of the next one. Buttons clean a room right away.
- **Rooms**: the rooms in priority order (the order breaks ties when several rooms could be cleaned), to reorder, skip, add, edit or delete. A room page shows its live status and its recent jobs next to the form.
- **History**: the jobs of the last 7 or 30 days, with their result (done, interrupted, failed, stopped) and a summary per room.
- **Settings**: quiet hours, wake-up check, how to drive the robot and how to tell that a job is over.

Times in the panel are estimates: a room that is empty now may be occupied in ten minutes.

## Card

The **Tidy Rooms card** (`custom:tidy-rooms-card`) shows the robot and the rooms in compact form on any dashboard, with a visual editor. It needs no resource to be added by hand.

```yaml
type: custom:tidy-rooms-card
entry_id: 01J...      # optional: the robot, when Tidy Rooms manages more than one
title: Cleaning       # optional
rooms: [01J..., 01J...]  # optional: which rooms, in the panel order (all by default)
show_robot: true
show_outlook: true
```

## Installation

### Marketplace (HACS)

1. Open the Marketplace, menu (⋮) → **Custom repositories**.
2. Add `https://github.com/salvatore-081/ha-tidy-rooms` as an **Integration**.
3. Install **Tidy Rooms** and restart Home Assistant.

Install a release: the panel and the card are built when a release is published and ship only in its zip (`tidy_rooms.zip`). Installed from a commit, the integration works without them.

### Manual

Download `tidy_rooms.zip` from the latest release, unpack it into `config/custom_components/tidy_rooms` and restart Home Assistant.

## Configuration

1. **Settings → Devices & services → Add integration → Tidy Rooms**, then choose the robot vacuum.
2. In the **Tidy Rooms** panel, **Rooms → Add room** for each room: area, presence sensors, targets and deadlines.
3. **Settings** in the panel for quiet hours, wake-up check, minimum battery and how to drive the robot (work mode select entity and its options for "vacuum and mop" and "vacuum only", normal and quiet fan speeds).

Rooms and settings can also be managed from the integration page (**Add room**, **Configure**): both edit the same configuration.

## Entities

For the whole robot:

| Entity | Description |
|---|---|
| `sensor.…_job` | `idle`, `starting`, `running`, `finishing`; attributes: room, kind, forced, quiet |
| `switch.…_automatic_cleaning` | Pauses automatic cleaning (a running job is not stopped) |

For each room (one device per room, in the room's area):

| Entity | Description |
|---|---|
| `sensor.…_status` | `done`, `ready`, `cleaning`, `waiting_occupied`, `waiting_gap`, `waiting_quiet_hours`, `waiting_awake`, `waiting_robot`, `disabled`; attributes: today's passes and targets, last result |
| `sensor.…_last_vacuum_and_mop`, `sensor.…_last_vacuum` | When the room last got each kind of pass |
| `switch.…_automatic_cleaning` | Skips the room |
| `button.…_vacuum_and_mop_now`, `button.…_vacuum_now` | Cleans the room now, even if occupied; counts towards today's targets |

## Custom clean action

Some robot integrations expose area cleaning but the robot rejects the command. For these, each room can have a **custom clean action** that replaces `vacuum.clean_area`. Work mode and fan speed are still set by Tidy Rooms before the action runs. Available variables: `room`, `area_id`, `kind` (`full` or `vacuum`), `quiet`, `vacuum_entity`.

Example for Ecovacs robots that need `clean_V2` (room id `2` in the Ecovacs app map):

```yaml
- action: vacuum.send_command
  target:
    entity_id: "{{ vacuum_entity }}"
  data:
    command: clean_V2
    params:
      act: start
      content:
        type: freeClean
        value: "1,2"
```

Write values like `"1,2"` literally. A template that renders to `1,2` is turned into a list by Home Assistant's native types, and the robot rejects it.

## Development

Backend:

```bash
uv venv --python 3.14
uv pip install "pytest-homeassistant-custom-component==0.13.375"
.venv/bin/python -m pytest
```

The planning rules live in `planner.py` as pure functions, without Home Assistant, and are tested on their own.

Frontend (Lit and TypeScript, built with Vite into `custom_components/tidy_rooms/frontend/`):

```bash
cd frontend
npm ci --ignore-scripts
npm run lint && npm run typecheck && npm test
npm run build
```

The panel talks to the integration through its WebSocket API (`websocket_api.py`, commands `tidy_rooms/*`); the forms are the integration's own schemas, shown with Home Assistant's `ha-form`.

## License

MIT
