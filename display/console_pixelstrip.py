from typing import List, Tuple, Optional

def Color(r: int, g: int, b: int) -> int:
    """
    Compatibility helper to create a 24-bit color integer like rpi_ws281x.Color.
    """
    r = max(0, min(255, int(r)))
    g = max(0, min(255, int(g)))
    b = max(0, min(255, int(b)))
    return (r << 16) | (g << 8) | b


class ConsolePixelStrip:
    """
    Simple Console replacement for rpi_ws281x.PixelStrip for debugging.

    - API compatible enough for ledbar_display.py:
      __init__(num, pin, freq_hz, dma, invert, brightness, channel)
      begin(), setPixelColor(idx, color), show(), numPixels()

    - Displays one overwritable line with colored block characters representing LEDs.
    - Accepts color as 24-bit int (from Color) or (r,g,b) tuple.
    - Brightness is ignored.
    """

    def __init__(self, num: int, pin: int = 18, freq_hz: int = 800000,
                 dma: int = 10, invert: bool = False, brightness: int = 255,
                 channel: int = 0):
        self._num = max(1, int(num))
        self._pin = pin
        self._brightness = brightness
        self._pixels: List[Tuple[int, int, int]] = [(0, 0, 0)] * self._num
        self._first_draw = True

    def begin(self):
        # No hardware init required for console strip
        return

    def numPixels(self) -> int:
        return self._num

    def _to_rgb_tuple(self, color) -> Tuple[int, int, int]:
        # Accept either (r,g,b) tuple or 24-bit int
        if color is None:
            return (0, 0, 0)
        if isinstance(color, tuple) or isinstance(color, list):
            r, g, b = int(color[0]), int(color[1]), int(color[2])
            return (max(0, min(255, r)),
                    max(0, min(255, g)),
                    max(0, min(255, b)))
        try:
            ival = int(color)
        except Exception:
            return (0, 0, 0)
        r = (ival >> 16) & 0xFF
        g = (ival >> 8) & 0xFF
        b = ival & 0xFF
        return (r, g, b)

    def setPixelColor(self, idx: int, color):
        if idx < 0 or idx >= self._num:
            return
        self._pixels[idx] = self._to_rgb_tuple(color)

    def setPixelColour(self, idx: int, color):  # alternate spelling if used
        self.setPixelColor(idx, color)

    def _ansi_fg_rgb(self, r: int, g: int, b: int) -> str:
        return f"\x1b[38;2;{r};{g};{b}m"

    def show(self):
        """
        Render a single line with one symbol per LED and overwrite previous line.
        Uses a filled circle '●' for lit pixels and a dim dot '·' for dark.
        """
        # Move cursor to start of line and clear it before printing (overwrite)
        if not self._first_draw:
            print("\x1b[2K\r", end="")
        else:
            self._first_draw = False

        out_parts: List[str] = []
        for (r, g, b) in self._pixels:
            if r == 0 and g == 0 and b == 0:
                # unlit
                out_parts.append("\x1b[90m·\x1b[0m")  # bright black / gray dot
            else:
                out_parts.append(f"{self._ansi_fg_rgb(r,g,b)}●\x1b[0m")

        print("".join(out_parts), end="", flush=True)

    # convenience to clear buffer
    def clear(self):
        self._pixels = [(0, 0, 0)] * self._num

    # allow using as context manager if desired
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        # Ensure cursor moved to new line when exiting so prompt is not overwritten
        print("\x1b[0m\n", end="")