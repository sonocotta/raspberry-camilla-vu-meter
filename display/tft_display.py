from typing import Optional, Dict, List, Union
import traceback
import os
import configparser

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
        style: str = "rainbow",
    ):
        self.width = int(width)
        self.height = int(height)
        # `mono` is determined from the meters.txt channels setting for the selected style
        self.mono = False
        self.style = style or "rainbow"

        self.device0 = device0
        self.device1 = device1

        self._font = None
        # try load small default font
        try:
            if ImageFont is not None:
                self._font = ImageFont.load_default()
        except Exception as e:
            print("Error loading default font:", e)
            self._font = None

        # attempt to determine style configuration (channels, background) before instantiation
        try:
            channels, bgr_path = self._read_style_config()
            if channels is not None:
                # INVERTED LOGIC: if meters.txt says channels=2 the meter image
                # already contains both channels and is meant for a single display
                # (render both channels on device0). If channels=1 the style
                # defines a mono meter image and we should initialize two
                # separate displays (one per audio channel) and render the
                # mono style on both.
                self.mono = (channels == 2)
            else:
                # default: assume two displays (channels=2 -> single display)
                self.mono = True
        except Exception:
            channels = None
            bgr_path = None

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
        except Exception as e:
            # initialization failed -> print and fall back to console prints
            traceback.print_exc()
            self.device0 = None
            self.device1 = None
        else:
            # If devices were created successfully, attempt to load and render background
            try:
                # render background if we found a path earlier
                if bgr_path:
                    self._render_background(bgr_path)
                else:
                    # fallback: try the older loader which will re-read meters.txt
                    self._load_and_render_style_background()
            except Exception:
                # non-fatal; continue without background
                traceback.print_exc()

    def _read_style_config(self):
        """Read meters.txt for this resolution and style.

        Returns (channels:int|None, bgr_path:str|None)
        """
        base_dir = os.path.join(os.path.dirname(__file__), "peppy", f"{self.width}x{self.height}")
        meters_path = os.path.join(base_dir, "meters.txt")
        if not os.path.exists(meters_path):
            return None, None

        cfg = configparser.RawConfigParser()
        try:
            with open(meters_path, "r", encoding="utf-8") as fh:
                cfg.read_file(fh)
        except Exception:
            return None, None

        section = None
        if cfg.has_section(self.style):
            section = self.style
        else:
            if cfg.has_section("rainbow"):
                section = "rainbow"

        if not section:
            return None, None

        # channels
        try:
            channels_raw = cfg.get(section, "channels", fallback=None)
            channels = int(channels_raw) if channels_raw is not None else None
        except Exception:
            channels = None

        try:
            bgr_name = cfg.get(section, "bgr.filename", fallback="").strip()
        except Exception:
            bgr_name = ""

        bgr_path = None
        if bgr_name:
            candidate = os.path.join(base_dir, bgr_name)
            if os.path.exists(candidate):
                bgr_path = candidate

        return channels, bgr_path

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

    def _load_and_render_style_background(self):
        """Load the meter style config and render the background image to attached TFT devices.

        Looks for `display/peppy/{width}x{height}/meters.txt`, finds the section named
        after `self.style` (e.g. 'rainbow'), reads `bgr.filename`, loads the image and
        displays it on both devices (or on device0 when mono).
        """
        # Preconditions
        if Image is None:
            return

        # Resolve meters.txt for this resolution
        base_dir = os.path.join(os.path.dirname(__file__), "peppy", f"{self.width}x{self.height}")
        meters_path = os.path.join(base_dir, "meters.txt")
        if not os.path.exists(meters_path):
            # nothing to do
            return

        cfg = configparser.RawConfigParser()
        try:
            with open(meters_path, "r", encoding="utf-8") as fh:
                cfg.read_file(fh)
        except Exception:
            return

        section = None
        if cfg.has_section(self.style):
            section = self.style
        else:
            # fallback to first matching section named 'rainbow' as default
            if cfg.has_section("rainbow"):
                section = "rainbow"

        if not section:
            return

        try:
            bgr_name = cfg.get(section, "bgr.filename", fallback="").strip()
        except Exception:
            bgr_name = ""

        if not bgr_name:
            return

        bgr_path = os.path.join(base_dir, bgr_name)
        if not os.path.exists(bgr_path):
            return

        try:
            img = Image.open(bgr_path).convert("RGB")
            if img.size != (self.width, self.height):
                img = img.resize((self.width, self.height))
        except Exception:
            return

        # Render to device(s)
        devs = [self.device0]
        if not self.mono:
            devs.append(self.device1)

        for dev in devs:
            if dev is None:
                continue
            try:
                dev.display(img)
            except Exception:
                # best-effort only
                traceback.print_exc()

    def _render_background(self, bgr_path: str):
        """Load a background image from absolute `bgr_path` and render it to the
        initialized TFT device(s).

        This is a small, focused helper used when `_read_style_config()` returns
        an explicit absolute path for the background file.
        """
        if Image is None:
            return
        if not bgr_path or not os.path.exists(bgr_path):
            return

        try:
            img = Image.open(bgr_path).convert("RGB")
            if img.size != (self.width, self.height):
                img = img.resize((self.width, self.height))
        except Exception:
            traceback.print_exc()
            return

        # Render according to current mono/double-display configuration.
        # If self.mono is True we render only to device0 (single combined image).
        # If self.mono is False we attempt to render the same mono-style image
        # to both device0 and device1 (one physical display per channel).
        targets = []
        if self.device0 is not None:
            targets.append(self.device0)
        if not self.mono and self.device1 is not None:
            targets.append(self.device1)

        for dev in targets:
            try:
                dev.display(img)
            except Exception:
                traceback.print_exc()

    def clear(self):
        """Clear any attached TFT displays (black screen)."""
        if Image is None:
            return
        for dev in (self.device0, self.device1):
            if dev is None:
                continue
            try:
                img = Image.new("RGB", (self.width, self.height), "black")
                dev.display(img)
            except Exception:
                # best-effort only
                traceback.print_exc()

    def close(self):
        """Clear and attempt any device cleanup."""
        try:
            self.clear()
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

    def _draw_text_on_image(self, label: str, rms: float, peak: float) -> Optional[object]:
        """Create a PIL image with simple text for the given label/rms/peak."""
        if Image is None or ImageDraw is None:
            return None
        img = Image.new("RGB", (self.width, self.height), "black")
        draw = ImageDraw.Draw(img)
        font = self._font

        # basic layout: label big-ish near top, then RMS and PEAK lines
        try:
            if font is None:
                # fallback approximate positions
                draw.text((10, 10), f"{label}", fill="white")
                draw.text((10, 40), f"RMS: {rms:.1f} dB", fill="white")
                draw.text((10, 70), f"PK : {peak:.1f} dB", fill="white")
            else:
                # label
                draw.text((10, 8), f"{label}", fill="white", font=font)
                # RMS / PEAK
                draw.text((10, 36), f"RMS: {rms:.1f} dB", fill="white", font=font)
                draw.text((10, 56), f"PK : {peak:.1f} dB", fill="white", font=font)
        except Exception:
            traceback.print_exc()
        return img

    def _draw_on_device(self, dev, label: str, rms: float, peak: float):
        """Render text and push to device; if no device, print to console."""
        img = self._draw_text_on_image(label, rms, peak)
        if img is None or dev is None:
            # fallback: console output
            print(f"{label} RMS:{rms:.1f} dB  PK:{peak:.1f} dB")
            return
        try:
            dev.display(img)
        except Exception:
            traceback.print_exc()
            print(f"{label} RMS:{rms:.1f} dB  PK:{peak:.1f} dB")

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

        try:
            if self.mono:
                avg_rms = (float(rms[0]) + float(rms[1])) / 2.0
                avg_peak = (float(peak[0]) + float(peak[1])) / 2.0
                # self._draw_on_device(self.device0, "LR", avg_rms, avg_peak)
            else:
                # channel 0 -> device0 labeled "L", channel 1 -> device1 labeled "R"
                self._draw_on_device(self.device0, "L", float(rms[0]), float(peak[0]))
                # self._draw_on_device(self.device1, "R", float(rms[1]), float(peak[1]))
        except Exception:
            traceback.print_exc()