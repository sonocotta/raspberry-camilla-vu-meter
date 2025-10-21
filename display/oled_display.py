from typing import Optional, Dict, List
import traceback
import math

try:
    from luma.core.interface.serial import spi as luma_spi  # type: ignore
    from luma.oled.device import sh1106  # type: ignore
    from luma.core.render import canvas  # type: ignore
    from PIL import ImageFont  # type: ignore
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
        min_db: float = -96.0,
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
            self._min_db = -96.0
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

        # load fonts: default and a larger truetype if available
        try:
            self._font = ImageFont.load_default()
        except Exception:
            self._font = None

        # try to load a larger truetype font for the big L/R; fallback to default
        try:
            # common path and generic font name; if not available fallback to default
            self._big_font = ImageFont.truetype("DejaVuSans.ttf", 24)
        except Exception:
            try:
                self._big_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
            except Exception:
                self._big_font = self._font

        # small 7px font for DB labels (try truetype first, then fallback)
        try:
            self._small_font = ImageFont.truetype("DejaVuSans.ttf", 7)
        except Exception:
            try:
                self._small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 7)
            except Exception:
                # final fallback: use default (may be larger than 6px)
                self._small_font = self._font

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

    def _text_size(self, draw, text: str, font):
        """
        Return (width, height) for rendered text using available APIs.
        """
        try:
            # Pillow >= 8.0: textbbox
            bbox = draw.textbbox((0, 0), text, font=font)
            return (bbox[2] - bbox[0], bbox[3] - bbox[1])
        except Exception:
            pass
        try:
            # older API or some backends
            size = draw.textsize(text, font=font)
            return size
        except Exception:
            pass
        try:
            # ImageFont newer APIs
            bbox = font.getbbox(text)
            return (bbox[2] - bbox[0], bbox[3] - bbox[1])
        except Exception:
            pass
        try:
            size = font.getsize(text)
            return size
        except Exception:
            pass
        # last resort: estimate
        return (len(text) * 6, 8)

    def _db_to_angle(self, db: float) -> float:
        """
        Map db in [min_db..max_db] to angle in radians.
        Center angle at 0, span = self.angle_span_deg degrees.
        """
        db = float(db)
        db = self._clamp(db, self._min_db, self._max_db)
        ratio = (db - self._min_db) / self._span_db  # 0..1
        half_span = self.angle_span_deg / 2.0
        angle_deg = (ratio * self.angle_span_deg) - half_span
        return math.radians(angle_deg)

    def _db_to_x(self, db: float, left: int, right: int) -> int:
        """
        Map db in [min_db..max_db] to an X coordinate between left..right (inclusive).
        """
        db = float(db)
        db = self._clamp(db, self._min_db, self._max_db)
        ratio = (db - self._min_db) / self._span_db  # 0..1
        return int(round(left + ratio * (right - left)))

    def _draw_meter(self, draw, rms: float, peak: float):
        """
        Draw a single needle meter on the provided draw object.
        - pivot is above the visible area at (cx, pivot_y)
        - needle length is self.needle_length
        """
        cx = self.width // 2
        # pivot above the screen: place it so needle originates outside and can sweep into view
        pivot_y = -int(self.needle_length * 0.2)

        # compute angle and endpoint
        angle = self._db_to_angle(rms)
        # angle 0 points downwards; we use angle measured from vertical
        # compute endpoint
        ex = int(cx + self.needle_length * math.sin(angle))
        ey = int(pivot_y + self.needle_length * math.cos(angle))

        # draw a thin line (needle)
        draw.line([(cx, pivot_y), (ex, ey)], fill="white")

    def _draw_on_device(self, device, label: str, rms: float, peak: float):
        if device is None or canvas is None:
            print(f"{label} RMS:{rms:6.1f} dB  Peak:{peak:6.1f} dB")
            return

        try:
            with canvas(device, dither=False) as draw:
                # large centered channel label (L or R) in the middle of the screen
                big_font = self._big_font or self._font
                label_w, label_h = self._text_size(draw, label, big_font)
                label_x = (self.width - label_w) // 2
                label_y = max(0, (self.height // 2) - (label_h // 2) - 16)
                draw.text((label_x, label_y), label, fill="white", font=big_font)

                # draw needle meter centered in upper area
                self._draw_meter(draw, rms, peak)

                # bottom bar area
                try:
                    left = 6
                    right = self.width - 6
                    bar_top = self.height - 14
                    bar_bottom = self.height - 11

                    # base bar (two horizontal lines)
                    draw.line((left, bar_top, right, bar_top), fill="white")
                    draw.line((left, bar_bottom, right, bar_bottom), fill="white")

                    # ticks helper
                    def draw_tick(x):
                        draw.line((x, bar_top - 3, x, bar_bottom + 3), fill="white")

                    # min and max ticks + numeric labels (numbers only), placed above the bar
                    draw_tick(left)
                    min_txt = f"{int(self._min_db)}"
                    min_w, min_h = self._text_size(draw, min_txt, self._small_font)
                    draw.text((left - (min_w // 2), bar_top - min_h - 4), min_txt, fill="white", font=self._small_font)

                    draw_tick(right)
                    max_txt = f"{int(self._max_db)}"
                    max_w, max_h = self._text_size(draw, max_txt, self._small_font)
                    draw.text((right - (max_w // 2), bar_top - max_h - 4), max_txt, fill="white", font=self._small_font)

                    # 0 dB marker (if within range) and numeric label
                    x0 = self._db_to_x(0.0, left, right)
                    draw_tick(x0)
                    zero_txt = "0"
                    z_w, z_h = self._text_size(draw, zero_txt, self._small_font)
                    draw.text((x0 - (z_w // 2), bar_top - z_h - 4), zero_txt, fill="white", font=self._small_font)

                    # additional step markers and labels for -12 dB steps below 0dB (12dB increments)
                    step_db = -12 
                    i = 1
                    while step_db >= self._min_db:
                        xs = self._db_to_x(step_db, left, right)
                        # shorter tick for intermediate steps
                        draw.line((xs, bar_top - 2, xs, bar_bottom + 2), fill="white")
                        lbl = f"{int(step_db)}"
                        lw, lh = self._text_size(draw, lbl, self._small_font)
                        draw.text((xs - (lw // 2), bar_top - lh - 4), lbl, fill="white", font=self._small_font)
                        step_db -= 12 * i
                        i *= 2

                    # RMS number centered above the bar
                    # small_y = bar_top - (z_h + 6)
                    # rms_txt = f"{rms:.1f}"
                    # rms_w, rms_h = self._text_size(draw, rms_txt, self._font)
                    # draw.text(((self.width - rms_w) // 2, small_y), rms_txt, fill="white", font=self._font)

                    # peak fill: fill from minimum (left) to peak position (only if peak > min_db)
                    if peak > self._min_db:
                        xp = self._db_to_x(peak, left, right)
                        x_start = left
                        x_end = xp
                        # ensure inside bounds
                        x_start = max(left, min(right, x_start))
                        x_end = max(left, min(right, x_end))
                        if x_end >= x_start:
                            # fill rectangle between bar lines
                            draw.rectangle((x_start, bar_top + 1, x_end, bar_bottom - 1), outline="white", fill="white")
                except Exception:
                    # fallback to numeric text if drawing fails
                    try:
                        draw.text((2, self.height - 16), f"{rms:.1f}", fill="white", font=self._font)
                        draw.text((self.width - 30, self.height - 16), f"{peak:.1f}", fill="white", font=self._font)
                    except Exception:
                        print(f"{label} RMS:{rms:6.1f} dB  Peak:{peak:6.1f} dB")
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
