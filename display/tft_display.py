from typing import Optional, Dict, List, Union
import traceback

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:
    Image = None  # type: ignore
    ImageDraw = None  # type: ignore
    ImageFont = None  # type: ignore

try:
    import st7735  # type: ignore
except Exception as e:
    st7735 = None  # type: ignore
    print("Error importing st7735:", e)

class TFTDisplay:
    """
    Basic TFT display driver (ST7735 based).

    - Initializes two ST7735 displays (one per channel) using provided SPI / GPIO pin parameters.
    - Provides clear() and close() methods and a minimal update(levels) that draws simple text:
      channel label (L/R), RMS and Peak values.
    - If st7735 or Pillow is unavailable, falls back to printing values to console.

    Parameters mirror the initialization style used by the project st7735 usage:
      spi_port0, cs0, dc0, rst (shared), backlight0, rotation0, width, height, spi_speed_hz, offset_left, offset_top
      spi_port1, cs1, dc1, backlight1, rotation1 (second device can omit rst/backlight if shared)
      mono: if True use single display (device0) and average L/R into a single "LR" readout.
    """

    def __init__(
        self,
        spi_port0: int = 0,
        cs0: int = 0,
        dc0: Union[int, str] = "GPIO25",
        rst: Optional[Union[int, str]] = "GPIO16",
        backlight0: Optional[Union[int, str]] = "GPIO18",
        rotation0: int = 0,
        spi_port1: int = 0,
        cs1: int = 1,
        dc1: Union[int, str] = "GPIO24",
        backlight1: Optional[Union[int, str]] = None,
        rotation1: int = 0,
        width: int = 320,
        height: int = 240,
        spi_speed_hz: int = 40_000_000,
        offset_left: int = 0,
        offset_top: int = 0,
        device0: Optional[object] = None,
        device1: Optional[object] = None,
        mono: bool = False,
        renderer_class: Optional[object] = None,
    ):
        self.width = int(width)
        self.height = int(height)
        self.mono = bool(mono)

        self.device0 = device0
        self.device1 = device1
        self._renderer = None

        self._font = None
        # try load small default font
        try:
            if ImageFont is not None:
                self._font = ImageFont.load_default()
        except Exception as e:
            print("Error loading default font:", e)
            self._font = None

        # attempt to instantiate st7735 displays if library available and devices not provided
        if st7735 is None:
            # library not available; fall back to console-only mode
            self.device0 = None
            self.device1 = None
            return

        try:
            if self.device0 is None:
                self.device0 = st7735.ST7735(
                    port=spi_port0,
                    cs=cs0,
                    dc=dc0,
                    rst=rst,
                    backlight=backlight0,
                    rotation=rotation0,
                    width=self.width,
                    height=self.height,
                    spi_speed_hz=spi_speed_hz,
                    offset_left=offset_left,
                    offset_top=offset_top,
                )
            if not self.mono and self.device1 is None:
                # second device - do not re-specify rst/backlight if your wiring shares them
                params = dict(
                    port=spi_port1,
                    cs=cs1,
                    dc=dc1,
                    rotation=rotation1,
                    width=self.width,
                    height=self.height,
                    spi_speed_hz=spi_speed_hz,
                    offset_left=offset_left,
                    offset_top=offset_top,
                )
                # include backlight if explicitly provided
                if backlight1 is not None:
                    params["backlight"] = backlight1
                self.device1 = st7735.ST7735(**params)
        except Exception:
            # initialization failed -> print and fall back to console prints
            traceback.print_exc()
            self.device0 = None
            self.device1 = None

        # instantiate renderer - lazy import to avoid hard dependency
        try:
            if renderer_class is None:
                # default to internal dummy renderer if available
                from .tft_renderer import TftRenderer as _DefaultRenderer  # type: ignore
                renderer_class = _DefaultRenderer
            # renderer gets devices and layout parameters
            self._renderer = renderer_class(self.device0, self.device1, width=self.width, height=self.height, mono=self.mono)
        except Exception:
            traceback.print_exc()
            self._renderer = None

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

    def clear(self):
        """Clear any attached TFT displays (black screen)."""
        if Image is None:
            return
        for dev in (self.device0, self.device1):
            if dev is None:
                continue
            try:
                img = Image.new("RGB", (self.width, self.height), "black")
                # many ST7735 libs expose display(image) or display(img)
                if hasattr(dev, "display") and callable(getattr(dev, "display")):
                    dev.display(img)
                elif hasattr(dev, "show") and callable(getattr(dev, "show")):
                    dev.show(img)
            except Exception:
                # best-effort only
                traceback.print_exc()

    def close(self):
        """Clear and attempt any device cleanup."""
        try:
            self.clear()
        except Exception:
            pass
        # let renderer do any cleanup it needs
        try:
            if self._renderer is not None and hasattr(self._renderer, "close"):
                self._renderer.close()
        except Exception:
            pass
        for dev in (self.device0, self.device1):
            if dev is None:
                continue
            try:
                if hasattr(dev, "cleanup") and callable(getattr(dev, "cleanup")):
                    dev.cleanup()
            except Exception:
                pass

    def update(self, levels):
        """
        Update displays with provided levels dictionary.
        Expects same keys as other displays: playback_rms / playback_peak or capture_*
        """
        data = self._prepare_levels(levels)
        if not data:
            return

        rms = data.get("playback_rms") or data.get("capture_rms") or []
        peak = data.get("playback_peak") or data.get("capture_peak") or []

        # ensure two channels present
        while len(rms) < 2:
            rms.append(-120.0)
        while len(peak) < 2:
            peak.append(-120.0)

        if self._renderer is not None and hasattr(self._renderer, "draw"):
            self._renderer.draw(float(rms[0]), float(peak[0]), float(rms[1]), float(peak[1]))
        else:
            print(f"L RMS:{float(rms[0]):.1f} dB  PK:{float(peak[0]):.1f} dB")
            print(f"R RMS:{float(rms[1]):.1f} dB  PK:{float(peak[1]):.1f} dB")