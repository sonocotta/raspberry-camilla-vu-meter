# Camilla DSP VU Meter

Small utility that reads level/peak information from CamillaDSP and displays a VU meter using:
- a pseudo-graphical console display (two channels),
- an `rpi_ws281x` LED strip (mono average of channels), required root,
- - alternatively, a color-LED simulation running in terminal
- or a dummy no-op display.

## Features

- Multiple displays can be active simultaneously (console + LED strip).
- LED coloring modes: whole-bar (color by dB) or end-colors (start green, last LEDs yellow/red).
- Fractional brightness for the last lit LED so level transitions look smooth.
- Peak marker shown on both console and LED strip (LED peak shown only if above configured min dB).
- Console debug PixelStrip implementation (ConsolePixelStrip) for debugging without hardware.

## Requirements

- Python 3.8+
- Linux (Raspberry Pi recommended for `rpi_ws281x`)
- Optional system package(s) for `rpi_ws281x` (require root to access PWM/GPIO)
- Repository requirements (pip): see `requirements.txt`

## Quick install (recommended inside project directory)

1. Create/activate virtual environment and install Python deps:
   ```bash
   cd ~/rpi-ws281x-camilla-vu-meter
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```
   If you want to use the real `rpi_ws281x` implementation, ensure the system has the required native libraries; installing `rpi_ws281x` via pip on a Raspberry Pi is typical.


## Running

- Console only:
  ```bash
  .venv/bin/python main.py --console --console-bar-length 40 --interval-ms 100
  ```
- LED bar (hardware) on GPIO 18 with 40 LEDs:
  ```bash
  sudo .venv/bin/python main.py --ledbar --led-pin 18 --led-count 40 --interval-ms 100
  ```
  Note: `sudo` / root may be required for hardware access depending on your setup.
- LED bar using console debug PixelStrip (no hardware required):
  ```bash
  .venv/bin/python main.py --ledbar --led-count 16 --led-console-debug --interval-ms 100
  ```
- Combine displays (console + LEDs):
  ```bash
  .venv/bin/python main.py --console --ledbar --led-count 8
  ```

### Available CLI options (examples; actual parser in `main.py`):

- --interval-ms N          update interval in milliseconds (default 100)
- --console                enable console pseudo-graphical display
- --console-bar-length N   console bar width in characters
- --ledbar                 enable rpi_ws281x LED bar display
- --led-pin N              GPIO pin for LED strip (default 18)
- --led-count N            number of LEDs on the strip (default 40)
- --led-console-debug      use ConsolePixelStrip (console visualization) instead of real PixelStrip
- --led-end-colors         enable end-colors mode (start green; last LEDs yellow/red)
- --led-min-db FLOAT       min dB mapped to first LED (default -120)
- --led-max-db FLOAT       max dB mapped to last LED (default 12)
- --dummy                  add dummy display (no-op)
- --host HOST              CamillaDSP host (default: localhost)
- --port PORT              CamillaDSP port (default: 1234)

### Example systemd service

- Place the unit file at `/etc/systemd/system/camillavumeter.service` (edit paths/user as needed).

```ini
[Unit]
Description=CamillaDSP VU Meter (rpi-ws281x)
After=network.target

[Service]
Type=simple
# Run as root if you need hardware access; otherwise set User=pi (or another user)
User=root
WorkingDirectory=/opt/rpi-ws281x-camilla-vu-meter
# Use the virtualenv python directly; run with LED hardware access (no sudo needed in systemd)
ExecStart=/opt/rpi-ws281x-camilla-vu-meter/.venv/bin/python /opt/rpi-ws281x-camilla-vu-meter/main.py --ledbar --led-pin 18 --led-count 40 --interval-ms 100
Restart=always
RestartSec=5
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=camillavumeter

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now camillavumeter.service
sudo journalctl -u camillavumeter -f
```

## Notes & troubleshooting

- `rpi_ws281x`: on Raspberry Pi you need root privileges to control PWM/GPIO using DMA.
- If you can't use hardware or want to debug visually, use `--led-console-debug` to render the LED strip state in the terminal.
- If the LED colors look inverted or wrong, check `PixelStrip` wiring and ordering; the console debug strip mirrors RGB color ordering used in the library.
- If CamillaDSP host/port differ, pass `--host` and `--port`. Default is `localhost:1234`
- Logs go to journal when run as a systemd service; when running manually, output goes to the terminal.

## Project layout (key files)

- main.py — entrypoint, command-line parsing and orchestrator
- display/
  - console_display.py — two-channel console VU
  - ledbar_display.py — rpi_ws281x LED bar implementation
  - console_pixelstrip.py — ConsolePixelStrip (debug PixelStrip replacement)
  - dummy_display.py — no-op display

## License

- GPL v3
