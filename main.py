import asyncio
import argparse
from camilladsp import CamillaClient
from display.console_display import ConsoleDisplay
from display.dummy_display import DummyDisplay
from display.ledbar_display import RpiWs281xDisplay


class CamillaVuMeter:
    def __init__(self, host="localhost", port=1234, update_interval=0.1, displays=None):
        self.host = host
        self.port = port
        self.update_interval = update_interval
        # accept single display or list
        if displays is None:
            self.displays = [ConsoleDisplay()]
        elif isinstance(displays, list):
            self.displays = displays
        else:
            self.displays = [displays]
        self.client = CamillaClient(host, port)

    async def run(self):
        self.client.connect()
        print(f"Connected to CamillaDSP at {self.host}:{self.port}")

        try:
            while True:
                try:
                    levels = self.client.levels
                    if levels:
                        for disp in self.displays:
                            try:
                                disp.update(levels)
                            except Exception as e:
                                # do not stop other displays on one failure
                                print(f"Display error ({disp.__class__.__name__}): {e}")
                    await asyncio.sleep(self.update_interval)
                except Exception as e:
                    print(f"Error fetching VU levels: {e}")
                    await asyncio.sleep(1)
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        finally:
            # clear displays on exit if they support clear()
            for disp in self.displays:
                try:
                    if hasattr(disp, "clear") and callable(getattr(disp, "clear")):
                        disp.clear()
                except Exception:
                    pass
            try:
                if hasattr(self.client, "close"):
                    self.client.close()
            except Exception:
                pass


async def main(args):
    displays = []

    # Console display
    if args.console:
        displays.append(ConsoleDisplay(bar_length=args.console_bar_length))

    # LED bar display
    if args.ledbar:
        displays.append(RpiWs281xDisplay(pin=args.led_pin,
                                         num_leds=args.led_count,
                                         console_strip=args.led_console_debug,
                                         end_colors=args.led_end_colors,
                                         min_db=args.led_min_db,
                                         max_db=args.led_max_db))

    # OLED display
    if args.oled:
        try:
            from display.oled_display import OledDisplay
            displays.append(OledDisplay(
                spi_port0=args.oled_spi_port0,
                spi_device0=args.oled_spi_device0,
                gpio_dc0=args.oled_dc0,
                spi_port1=args.oled_spi_port1,
                spi_device1=args.oled_spi_device1,
                gpio_dc1=args.oled_dc1,
                gpio_rst=args.oled_rst,
                needle_length=args.oled_needle_length,
                min_db=args.oled_min_db,
                max_db=args.oled_max_db,
                mono=args.oled_mono,
            ))
        except Exception as e:
            print(f"OLED display not available or failed to initialize: {e}")

    # TFT display
    if args.tft:
        try:
            from display.tft_display import TFTDisplay
            displays.append(TFTDisplay(
                spi_port0=args.tft_spi_port0,
                cs0=args.tft_cs0,
                dc0=args.tft_dc0,
                rst=args.tft_rst,
                backlight0=args.tft_backlight0,
                rotation0=args.tft_rotation0,
                spi_port1=args.tft_spi_port1,
                cs1=args.tft_cs1,
                dc1=args.tft_dc1,
                backlight1=args.tft_backlight1,
                rotation1=args.tft_rotation1,
                width=args.tft_width,
                height=args.tft_height,
                spi_speed_hz=args.tft_spi_speed_hz,
                offset_left=args.tft_offset_left,
                offset_top=args.tft_offset_top,
                mono=args.tft_mono,
            ))
        except Exception as e:
            print(f"TFT display not available or failed to initialize: {e}")

    # Dummy display
    if args.dummy:
        displays.append(DummyDisplay())

    # If no display flags given, default to console
    if not displays:
        displays.append(ConsoleDisplay())

    vu_meter = CamillaVuMeter(
        host=args.host,
        port=args.port,
        update_interval=args.interval_ms / 1000.0,
        displays=displays
    )

    await vu_meter.run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CamillaDSP VU meter")
    parser.add_argument("--interval-ms", type=int, default=100,
                        help="Update interval in milliseconds (default: 100)")

    parser.add_argument("--ledbar", action="store_true",
                        help="Enable rpi_ws281x LED bar display")
    parser.add_argument("--led-pin", type=int, default=18,
                        help="GPIO pin for LED strip (default: 18)")
    parser.add_argument("--led-count", type=int, default=40,
                        help="Number of LEDs on the strip (default: 40)")
    parser.add_argument("--led-console-debug", action="store_true",
                        help="Use console pixel strip for LED bar display (for debugging)")
    parser.add_argument("--led-end-colors", action="store_true",
                        help="Use end-based coloring for LED bar display (start green, end red)")
    parser.add_argument("--led-min-db", type=float, default=-102.0,
                        help="Minimum dB for LED bar display (default: -102.0)")
    parser.add_argument("--led-max-db", type=float, default=6.0,
                        help="Maximum dB for LED bar display (default: 6.0)")

    parser.add_argument("--oled", action="store_true",
                        help="Enable OLED display")
    parser.add_argument("--oled-mono", action="store_true",
                        help="Enable mono OLED mode (single display labeled 'LR' using averaged L/R values)")
    parser.add_argument("--oled-spi-port0", type=int, default=0,
                        help="SPI port for device0 (default: 0)")
    parser.add_argument("--oled-spi-device0", type=int, default=0,
                        help="SPI device number for device0 (default: 0)")
    parser.add_argument("--oled-dc0", type=int, default=25,
                        help="DC GPIO for device0 (default: 25)")
    parser.add_argument("--oled-spi-port1", type=int, default=0,
                        help="SPI port for device1 (default: 0)")
    parser.add_argument("--oled-spi-device1", type=int, default=1,
                        help="SPI device number for device1 (default: 1)")
    parser.add_argument("--oled-dc1", type=int, default=24,
                        help="DC GPIO for device1 (default: 24)")
    parser.add_argument("--oled-rst", type=int, default=16,
                        help="Shared RST GPIO for both OLEDs (passed for first device only; default: 16)")
    parser.add_argument("--oled-needle-length", type=int, default=80,
                        help="Needle length in pixels for OLED meter (default: 80)")
    parser.add_argument("--oled-min-db", type=float, default=-96.0,
                        help="Minimum dB mapped to left end of OLED bar (default: -96.0)")
    parser.add_argument("--oled-max-db", type=float, default=12.0,
                        help="Maximum dB mapped to right end of OLED bar (default: 12.0)")

    parser.add_argument("--tft", action="store_true",
                        help="Enable TFT displays (ST7735)")
    parser.add_argument("--tft-mono", action="store_true",
                        help="Enable mono TFT mode (single display labeled 'LR' using averaged L/R values)")
    parser.add_argument("--tft-spi-port0", type=int, default=0,
                        help="SPI port for TFT device0 (default: 0)")
    parser.add_argument("--tft-cs0", type=int, default=0,
                        help="Chip-select for TFT device0 (default: 0)")
    parser.add_argument("--tft-dc0", default="GPIO25",
                        help="DC pin for TFT device0 (default: GPIO25)")
    parser.add_argument("--tft-rst", default="GPIO16",
                        help="RST pin for TFT devices (shared; default: GPIO16)")
    parser.add_argument("--tft-backlight0", default="GPIO18",
                        help="Backlight pin for TFT device0 (default: GPIO18)")
    parser.add_argument("--tft-rotation0", type=int, default=0,
                        help="Rotation for TFT device0 (default: 0)")

    parser.add_argument("--tft-spi-port1", type=int, default=0,
                        help="SPI port for TFT device1 (default: 0)")
    parser.add_argument("--tft-cs1", type=int, default=1,
                        help="Chip-select for TFT device1 (default: 1)")
    parser.add_argument("--tft-dc1", default="GPIO24",
                        help="DC pin for TFT device1 (default: GPIO24)")
    parser.add_argument("--tft-backlight1", default=None,
                        help="Backlight pin for TFT device1 (optional)")
    parser.add_argument("--tft-rotation1", type=int, default=0,
                        help="Rotation for TFT device1 (default: 0)")

    parser.add_argument("--tft-width", type=int, default=320,
                        help="TFT width in pixels (default: 320)")
    parser.add_argument("--tft-height", type=int, default=240,
                        help="TFT height in pixels (default: 240)")
    parser.add_argument("--tft-spi-speed-hz", type=int, default=40_000_000,
                        help="SPI speed for TFT in Hz (default: 40_000_000)")
    parser.add_argument("--tft-offset-left", type=int, default=0,
                        help="TFT offset left (default: 0)")
    parser.add_argument("--tft-offset-top", type=int, default=0,
                        help="TFT offset top (default: 0)")

    parser.add_argument("--console", action="store_true",
                        help="Enable console pseudo-graphical display")
    parser.add_argument("--console-bar-length", type=int, default=40,
                        help="Console bar length in characters (default: 40)")

    parser.add_argument("--dummy", action="store_true",
                        help="Enable dummy (no-op) display")

    parser.add_argument("--host", default="localhost",
                        help="CamillaDSP host (default: localhost)")
    parser.add_argument("--port", type=int, default=1234,
                        help="CamillaDSP port (default: 1234)")

    args = parser.parse_args()
    asyncio.run(main(args))