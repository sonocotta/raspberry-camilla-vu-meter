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
            displays.append(OledDisplay())
        except ImportError:
            print("luma.oled not available, skipping OLED display.")

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