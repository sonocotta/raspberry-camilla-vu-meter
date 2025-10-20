# Camilla DSP VU Meter

Small utility that reads level/peak information from CamillaDSP and displays a VU meter using:
- a pseudo-graphical console display (two channels),
- an `rpi_ws281x` LED strip (mono average of channels), required root,
- - alternatively, a color-LED simulation running in terminal
- an OLED pair (SH1106) driven via SPI (one display per channel)
- or a dummy no-op display.

## Features

- Multiple displays can be active simultaneously (console + LED strip + OLED).
- LED coloring modes: whole-bar (color by dB) or end-colors (start green, last LEDs yellow/red).
- Fractional brightness for the last lit LED so level transitions look smooth.
- Peak marker shown on both console and LED strip (LED peak shown only if above configured min dB).
- OLED pair shows a large channel indicator and a needle meter plus a horizontal level bar with ticks and peak fill.
- Console debug PixelStrip implementation (ConsolePixelStrip) for debugging without hardware.

## Requirements

- Python 3.8+
- Linux (Raspberry Pi recommended for `rpi_ws281x`)
- Optional system package(s) for `rpi_ws281x` (require root to access PWM/GPIO)
- Repository requirements (pip): see `requirements.txt` (includes `luma.oled`, `Pillow`, `spidev`)

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

## OLED (SH1106) display details

This project supports driving two separate SH1106 SPI OLED devices (one device per audio channel) using the `luma.oled` library.

- Hardware wiring example (defaults used in code):
  - device1 (channel 0 shown as "L"): SPI device=1, port=0, DC=24, shared RST=16
  - device0 (channel 1 shown as "R"): SPI device=0, port=0, DC=25, shared RST=16

- Example initialization (internal code uses luma.core.interface.serial.spi + sh1106):
  ```python
  from luma.core.interface.serial import spi
  from luma.oled.device import sh1106

  serial1 = spi(device=1, port=0, gpio_DC=24, gpio_RST=16)  # RST only on first device
  serial0 = spi(device=0, port=0, gpio_DC=25)               # no gpio_RST here (shared)
  device1 = sh1106(serial1, rotate=0, width=128, height=64)  # shows channel 0 ("L")
  device0 = sh1106(serial0, rotate=0, width=128, height=64)  # shows channel 1 ("R")
  ```

- Implementation notes:
  - The OLEDs share a single RST line. The library constructor passes gpio_RST only when creating the first device; the second device is opened without gpio_RST.
  - Channel mapping: channel 0 is presented on the first device (label "L"), channel 1 on the second (label "R") — the code intentionally swaps devices to match common wiring.
  - Display layout:
    - Large centered "L" / "R" indicator in the middle.
    - Needle meter: pivot is a virtual point above the visible screen, needle length is configurable.
    - Bottom two-line horizontal bar with ticks and numeric labels (numbers only) printed above the bar.
    - Labels for 0 dB and additional ticks at -12 dB steps below 0 dB are drawn.
    - Peak is represented as a filled area from the left (min dB) to the peak position.
  - Configurable parameters (constructor / CLI examples):
    - min_db (default -102)
    - max_db (default 6)
    - needle_length (px)
    - angle_span_deg (deg)
    - spi ports/devices and gpio DC/RST pins (gpio_rst is a single shared RST)
  - The display requires `luma.oled` and `Pillow` installed; the code will raise an error if luma is missing.

## Running

- Console only:
  ```bash
  .venv/bin/python main.py --console --console-bar-length 40 --interval-ms 100
  ```

  <img width="944" height="83" alt="image" src="https://github.com/user-attachments/assets/5c429980-0420-4b79-b318-d66b9d8efb40" />

- OLED Hat (over SPI):
  ```bash
  sudo .venv/bin/python main.py --oled --interval-ms 100
  ```

  <img width="568" height="338" alt="image" src="https://github.com/user-attachments/assets/8c4b0a3d-6599-4f56-96a8-1d1e43914d36" />


- LED bar (hardware) on GPIO 18 with 40 LEDs:
  ```bash
  sudo .venv/bin/python main.py --ledbar --led-pin 18 --led-count 40 --interval-ms 100
  ```
  Note: `sudo` / root may be required for hardware access depending on your setup.

   <img width="864" height="658" alt="image" src="https://github.com/user-attachments/assets/3bb7696b-07f4-4b08-952c-2eeb38915ee8" />


- LED bar using console debug PixelStrip (no hardware required):
  ```bash
  .venv/bin/python main.py --ledbar --led-count 16 --led-console-debug --interval-ms 100
  ```

   <img width="1015" height="87" alt="image" src="https://github.com/user-attachments/assets/2f9cfb55-02cf-4d3f-bff7-5b480d23abb8" />
  
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
- --oled                   enable OLED pair display
- --oled-spi-port0 N       SPI port for device0 (example)
- --oled-spi-device0 N     SPI device number for device0 (example)
- --oled-dc0 N             DC GPIO for device0
- --oled-spi-port1 N       SPI port for device1 (example)
- --oled-spi-device1 N     SPI device number for device1 (example)
- --oled-dc1 N             DC GPIO for device1
- --oled-rst N             shared RST GPIO (single pin used for the first device)
- --oled-needle-length N   needle length in pixels
- --oled-min-db FLOAT      min dB mapped to left end of OLED bar (default -102)
- --oled-max-db FLOAT      max dB mapped to right end of OLED bar (default 6)
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
- `luma.oled`: SPI access requires spidev kernel support and correct wiring. The RST pin is shared between the two OLEDs — provide the gpio_rst value once.
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
  - oled_display.py — SH1106 OLED pair driver (needle + bar)
  - dummy_display.py — no-op display

## License

- GPL v3
