# Copilot instructions for this repository

Purpose: make an AI coding agent immediately productive when working on the CamillaDSP VU Meter (PeppyMeter) project.

Keep this file short and focused — reference real files and examples so the agent can act without guessing.

1) Big picture (quick)
- main.py is the orchestrator: it parses CLI flags, constructs a CamillaClient (network source) and one or more display objects, then runs the event loop that polls `client.levels` and calls `display.update(levels)`.
- Displays live under `display/` and are pluggable: `console_display.py`, `ledbar_display.py`, `oled_display.py`, `tft_display.py`, `dummy_display.py` and helpers like `console_pixelstrip.py`.
- `display/peppy-tft/` contains the Peppy meter renderer and configuration data (meter definitions per resolution in `display/peppy-tft/*/meters.txt`).

2) Minimal developer contract (what the agent can rely on)
- A display object must implement an update(levels) method. `main.py` passes `levels = self.client.levels` directly to displays.
- Displays MAY implement clear() which is called on shutdown if present. Always check with hasattr before calling.
- CLI flags are defined in `main.py`'s argparse block — add CLI options there if you add features.
- Channel indexing: code expects two channels by default. Mono modes (`--oled-mono`, `--tft-mono`) average L/R values. Channel-to-device mapping is intentionally swapped in the OLED code to match typical wiring (see `display/oled_display.py` and README notes).

3) Key files and what they show (use these as starting points)
- `main.py` — entrypoint, CLI, orchestration, sample usage and default flags.
- `README.md` — runtime/hardware notes, examples to reproduce locally (virtualenv, pip install, sudo for hardware), and systemd unit example.
- `display/*.py` — implementations of display backends. Look at `console_pixelstrip.py` for a hardware-free, inspectable PixelStrip simulation.
- `display/peppy-tft/` — meter renderer code and `*/meters.txt` files that define meter parameters (start/stop angles, files, origins). Example: `display/peppy-tft/320x240/meters.txt`.

4) Run & debug workflows (short, exact)
- Create venv and install deps: `python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt` (this repo requires Python 3.8+).
- Console-only test (no hardware): run `python main.py --console` (use `--interval-ms` and `--console-bar-length` to tune frequency/size).
- LED debug (no hardware): `python main.py --ledbar --led-count 16 --led-console-debug` — uses `ConsolePixelStrip`.
- OLED/TFT/LED hardware runs often require root access for SPI/GPIO (or run via systemd as root). See `README.md` systemd example.

5) Project-specific patterns and gotchas
- Shared RST pin for OLEDs: code passes gpio_rst only to the first device; the second opens without RST — reflect this when changing `oled_display.py` or wiring docs.
- When adding a new display backend, follow the display contract (update + optional clear), and wrap imports/initialization in try/except as in `main.py` so failures don't break other displays.
- Meter definitions live in `display/peppy-tft/*/meters.txt`. These are INI-like sections (e.g. `[rainbow]`) and are consumed by the Peppy renderer. Add new meters by editing the appropriate resolution folder and adding images referenced by `bgr.filename`, `indicator.filename`, etc.
- Hardware vs simulation: prefer adding or re-using the console debug implementations (`console_pixelstrip.py`, `console_display.py`) so CI and development don't need hardware.

6) Integration points and external deps (what to watch for)
- CamillaDSP network API: defaults to `localhost:1234` (flags `--host`/`--port`). Code reads `client.levels` — emulate it in tests or use a stubbed client for unit work.
- `rpi_ws281x` for LEDs, `luma.oled` for SH1106, `st7735` drivers for TFT — these require system/kernel support and often root access.
- Pillow (`PIL`) is used by display renderers; image assets and meter sprite caches are in `display/peppy-tft/`.

7) Useful search hooks (quick grep targets)
- "class .*Display" or filenames under `display/` to find backends
- `client.levels` and `CamillaClient` to find data source behavior
- `meters.txt` under `display/peppy-tft/*/` to find meter definitions to edit or extend

If anything here is unclear or you'd like examples added (e.g. a minimal unit-test stub for `CamillaClient` or a code patch template for new displays), tell me which area to expand and I will update this file.
