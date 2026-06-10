# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Meshtastic high-altitude balloon (HAB) bot that runs on a Raspberry Pi alongside `meshtasticd`. It broadcasts flight status (liftoff, altitude milestones, burst detection) over the mesh, replies to direct messages with telemetry and distance-to-sender, and periodically downlinks JSON telemetry on a dedicated "BalloonData" channel (index 1, prefixed `mtf1:`).

There are no tests, no linter config, and no requirements file. Dependencies (installed manually into a venv on the Pi, `/home/trick/mt` per the service files): `meshtastic`, `pypubsub`, `pyserial`.

## Running

- `python3 bot.py` — the main bot. Requires `config.py` (copy from `config.py.example`), which defines `my_name`, the `interface` object (BLE/TCP/serial connection to the node), and `use_balloondata_channel`. `config.py` is gitignored because it holds per-node/per-flight settings.
- `python3 cgps.py --port /dev/ttyACM0 --get-model | --set-flight-mode | --reboot` — standalone CLI to query/set the u-blox GPS dynamic model. Flight mode (airborne <1g) is required for the GPS to work above ~12km altitude.
- `gps.py` — small test harness for the vendored `ublox.py` library; not used by the bot.

Deployment is via systemd on the Pi: `balloon-bot.service` runs `bot.py`; `gps-setup.service` is a oneshot that sets GPS flight mode before `meshtasticd` starts.

## Architecture

`bot.py` is a single script with two concurrent concerns:

1. **Receive path** — `pub.subscribe(onReceive, "meshtastic.receive")` handles incoming packets via the meshtastic pubsub API. Every packet goes through `debug_print_packet()` for structured logging; text messages addressed to the connected node (its live ID via `interface.myInfo`) get an auto-reply with SNR/RSSI, current position, and great-circle distance (computed via ECEF conversion in `distance_between_geodetic_points`).

2. **Transmit loop** — the `while True` loop at the bottom runs every 60s. It reads GPS **not** from the meshtastic API but by regex-scraping `journalctl -u meshtasticd` output (`parse_recent_gps_from_journalctl`) — this is a deliberate workaround because the node's position API was unreliable. It tracks `max_alt`/`burst` state to fire one-shot announcements at altitude bands (the `alt > N and alt < N+360` windows assume ~6 m/s ascent × 60s loop, so each band triggers exactly once), and sends the JSON telemetry downlink on channel index 1.

Because GPS comes from journalctl, `bot.py` only works on the Pi next to a running `meshtasticd`; expect that and the BLE interface to be unavailable when developing elsewhere.

`ublox.py` is a vendored third-party library (tridge's pyUblox, GPL) — avoid editing it. `cgps.py` is self-contained and does not import it.

## Conventions

- `config.py` is the only place for per-node/per-flight settings (node name, node ID, interface type, channel flags). Don't hardcode these in `bot.py`.
- Logging is plain `print()`; systemd captures stdout (`PYTHONUNBUFFERED=1` in the service file).
