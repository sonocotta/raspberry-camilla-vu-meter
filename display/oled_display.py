from typing import Optional, Dict, List
import traceback
import math

try:
    from luma.core.interface.serial import spi as luma_spi  # type: ignore
    from luma.oled.device import sh1106  # type: ignore
    from luma.core.render import canvas  # type: ignore
    from PIL import ImageFont  # type: ignore
    from .oled_renderer import OledRenderer
except Exception as e:
    luma_spi = None  # type: ignore
    sh1106 = None  # type: ignore
    canvas = None  # type: ignore
    ImageFont = None  # type: ignore
    raise RuntimeError("luma.oled (and PIL) are required for OledDisplay: " + str(e))


class OledDisplay:
    """
    OLED display driver using luma.oled.sh1106 for two separate SPI devices (one per channel).

    - Swapped channels: device0 shows channel 1 (R), device1 shows channel 0 (L).
    - Needle meter with configurable range and length.
    - Bottom two-line horizontal bar with DB labels (small 6px height) above the bar.
    - Peak fills from the minimum (left end) to the peak position.
    """

    def __init__(
        self,
        spi_port0: int = 0,
        spi_device0: int = 0,
        gpio_dc0: int = 25,
        spi_port1: int = 0,
        spi_device1: int = 1,
        gpio_dc1: int = 24,
        gpio_rst: int = 16,                # single shared RST pin (only passed for first device)
        rotate: int = 0,
        width: int = 128,
        height: int = 64,
        device0: Optional[object] = None,
        device1: Optional[object] = None,
        min_db: float = -72.0,
        max_db: float = 12.0,
        needle_length: int = 80,
        angle_span_deg: float = 120.0,
        mono: bool = False,
    ):
        self.device0 = device0
        self.device1 = device1
        self._font = None
        self._big_font = None
        self._small_font = None
        self.width = int(width)
        self.height = int(height)
        self._min_db = float(min_db)
        self._max_db = float(max_db)
        if self._max_db <= self._min_db:
            self._min_db = -72.0
            self._max_db = 12.0
        self._span_db = self._max_db - self._min_db
        self.needle_length = max(1, int(needle_length))
        # angle span centered at 0 (so angles go from -angle_span/2 .. +angle_span/2)
        self.angle_span_deg = float(angle_span_deg)
        # mono mode: single-OLED showing combined LR values (label "LR")
        self.mono = bool(mono)

        # attempt to create devices via luma if not provided
        try:
            if self.device0 is None:
                # pass gpio_RST only for the first device (shared reset)
                serial0 = luma_spi(device=spi_device0, port=spi_port0, gpio_DC=gpio_dc0, gpio_RST=gpio_rst)
                self.device0 = sh1106(serial0, rotate=rotate, width=width, height=height)
            # create second device only when not in mono mode and not provided by caller
            if not self.mono and self.device1 is None:
                # do not pass gpio_RST for the second device (shared line)
                serial1 = luma_spi(device=spi_device1, port=spi_port1, gpio_DC=gpio_dc1)
                self.device1 = sh1106(serial1, rotate=rotate, width=width, height=height)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize SH1106 devices: {e}")

        # renderer encapsulates all drawing and font handling
        self._renderer = OledRenderer(
            width=self.width,
            height=self.height,
            min_db=self._min_db,
            max_db=self._max_db,
            needle_length=self.needle_length,
            angle_span_deg=self.angle_span_deg,
        )

    def _prepare_levels(self, levels) -> Optional[Dict[str, List[float]]]:
        if not levels:
            return None
        if isinstance(levels, dict):
            return levels
        try:
            if hasattr(levels, "levels") and callable(levels.levels):
                return levels.levels()
        except Exception:
            return None
        return None

    def _clamp(self, v: float, lo: float, hi: float) -> float:
        return lo if v < lo else (hi if v > hi else v)

    def _draw_on_device(self, device, label: str, rms: float, peak: float):
        if device is None or canvas is None:
            print(f"{label} RMS:{rms:6.1f} dB  Peak:{peak:6.1f} dB")
            return

        try:
            with canvas(device, dither=False) as draw:
                # delegate full rendering to the renderer
                self._renderer.render(draw, label, rms, peak)
        except Exception as e:
            try:
                print(f"{label} RMS:{rms:6.1f} dB  Peak:{peak:6.1f} dB")
            except Exception:
                traceback.print_exc()

    def update(self, levels):
        """
        Draw channel 0 -> device1 labeled 'L' and channel 1 -> device0 labeled 'R'
        (channels swapped compared to earlier behaviour).

        In mono mode (self.mono == True) draws single display on device0 with label "LR"
        and uses average of both channels for rms and peak.
        """
        data = self._prepare_levels(levels)
        if not data:
            return

        rms = data.get("playback_rms") or data.get("capture_rms") or []
        peak = data.get("playback_peak") or data.get("capture_peak") or []

        # ensure two channels present
        while len(rms) < 2:
            rms.append(self._min_db)
        while len(peak) < 2:
            peak.append(self._min_db)

        try:
            if self.mono:
                # average both channels and draw on single device (device0) labeled "LR"
                avg_rms = (float(rms[0]) + float(rms[1])) / 2.0
                avg_peak = (float(peak[0]) + float(peak[1])) / 2.0
                self._draw_on_device(self.device0, "LR", avg_rms, avg_peak)
            else:
                # swapped: channel 0 -> device1 labeled "L"; channel 1 -> device0 labeled "R"
                self._draw_on_device(self.device1, "L", float(rms[0]), float(peak[0]))
                self._draw_on_device(self.device0, "R", float(rms[1]), float(peak[1]))
        except Exception:
            traceback.print_exc()
