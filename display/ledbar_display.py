from typing import Dict, List, Optional
import math

try:
    from rpi_ws281x import PixelStrip, Color
except Exception:
    PixelStrip = None  # type: ignore
    Color = None  # type: ignore

class RpiWs281xDisplay:
    """
    LED bar display using rpi_ws281x.

    - Accepts gpio pin and number of LEDs.
    - Shows mono level (average of two channels).
    - Maps dB range [min_db..max_db] to LED count (dB is already log scale).
    - Top 1/8 of the dB range -> red, next 1/8 -> yellow, rest -> green.
    - Peak position is shown as blue (overrides color at that LED).

    New constructor parameters:
      console_strip (bool): if True, use display.console_pixelstrip.ConsolePixelStrip
                           and its Color() for debugging instead of real PixelStrip.
      min_db (float): bottom of dB range (default -96.0)
      max_db (float): top of dB range (default 12.0)
      end_colors (bool): if True, coloring is based on LED position so that
                         starting LEDs are always green and only the last LEDs
                         (top 1/8 and next 1/8) are yellow/red when lit.
    """

    def __init__(self, pin: int = 12, num_leds: int = 8, brightness: int = 255,
                 freq_hz: int = 800000, dma: int = 10, invert: bool = False, channel: int = 0,
                 console_strip: bool = False, min_db: float = -102.0, max_db: float = 6.0,
                 end_colors: bool = False):
        self.num_leds = max(1, int(num_leds))
        self.pin = int(pin)
        self.brightness = max(0, min(255, int(brightness)))
        self.freq_hz = freq_hz
        self.dma = dma
        self.invert = invert
        self.channel = channel

        # configurable dB range
        self._min_db = float(min_db)
        self._max_db = float(max_db)
        if self._max_db <= self._min_db:
            # fallback to sensible defaults if user passed invalid values
            self._min_db = -102.0
            self._max_db = 6.0
        self._span_db = self._max_db - self._min_db

        # coloring mode: when True, use end-based coloring (start green, last LEDs yellow/red)
        self._end_colors = bool(end_colors)

        self._strip = None
        self._color_fn = None

        # choose strip implementation: real PixelStrip or ConsolePixelStrip for debugging
        if console_strip:
            try:
                # local import to avoid requiring console helper when not used
                from .console_pixelstrip import ConsolePixelStrip, Color as ConsoleColor  # type: ignore
                strip_cls = ConsolePixelStrip
                color_fn = ConsoleColor
            except Exception as e:
                print(f"Warning: Failed to import ConsolePixelStrip: {e}")
                strip_cls = None
                color_fn = None
        else:
            strip_cls = PixelStrip
            color_fn = Color

        self._color_fn = color_fn

        if strip_cls is not None:
            try:
                # initialize strip (ConsolePixelStrip signature matches expected args)
                self._strip = strip_cls(self.num_leds, self.pin, self.freq_hz, self.dma, self.invert,
                                         self.brightness, self.channel)
                try:
                    # some implementations provide begin()
                    self._strip.begin()
                except Exception:
                    pass
            except Exception as e:
                print(f"Warning: Failed to initialize PixelStrip implementation: {e}")
                self._strip = None

    def _clamp(self, v: float, lo: float, hi: float) -> float:
        return lo if v < lo else (hi if v > hi else v)

    def _db_to_leds(self, db: float) -> int:
        db = self._clamp(db, self._min_db, self._max_db)
        ratio = (db - self._min_db) / self._span_db
        return int(round(ratio * self.num_leds))

    def _db_to_leds_float(self, db: float) -> float:
        """
        Map dB to a continuous LED count in range [0..num_leds].
        Useful to compute fractional brightness for the last lit LED.
        """
        db = self._clamp(db, self._min_db, self._max_db)
        ratio = (db - self._min_db) / self._span_db
        return ratio * self.num_leds

    def _color_for_db(self, db: float):
        """
        Determine color by splitting the dB span into 8 equal parts (in dB units).
        - top 1/8 -> red
        - next 1/8 -> yellow
        - rest -> green

        This function is used in "whole-bar" coloring mode. When end_colors is True,
        per-LED color logic based on position is applied instead (see update()).
        """
        db = float(db)
        # clamp first
        db = self._clamp(db, self._min_db, self._max_db)

        top_edge = self._max_db
        one_eighth = self._span_db / 8.0
        red_threshold = top_edge - one_eighth
        yellow_threshold = top_edge - (2.0 * one_eighth)

        if db > red_threshold:
            return (255, 0, 0)       # red
        if db > yellow_threshold:
            return (255, 255, 0)     # yellow
        return (0, 255, 0)           # green

    def _set_pixel(self, idx: int, rgb):
        if self._strip is None or self._color_fn is None:
            return
        r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
        try:
            self._strip.setPixelColor(idx, self._color_fn(r, g, b))
        except Exception:
            # some debug strips might accept a tuple directly
            try:
                self._strip.setPixelColor(idx, (r, g, b))
            except Exception:
                pass

    def _clear_strip(self):
        if self._strip is None:
            return
        for i in range(self.num_leds):
            try:
                if self._color_fn is not None:
                    self._strip.setPixelColor(i, self._color_fn(0, 0, 0))
                else:
                    self._strip.setPixelColor(i, (0, 0, 0))
            except Exception:
                pass

    def update(self, levels):
        """
        levels: dict as returned by Levels.levels() or an object exposing .levels()
        Uses playback_rms/playback_peak (falls back to capture_*).
        """
        if not levels:
            return

        data = None
        if isinstance(levels, dict):
            data = levels
        else:
            try:
                if hasattr(levels, "levels") and callable(levels.levels):
                    data = levels.levels()
            except Exception:
                data = None

        if not data:
            return

        rms = data.get("playback_rms") or data.get("capture_rms") or []
        peak = data.get("playback_peak") or data.get("capture_peak") or []

        # ensure at least two channels for averaging; pad with very low values if missing
        while len(rms) < 2:
            rms.append(self._min_db)
        while len(peak) < 2:
            peak.append(self._min_db)

        # mono level = average of first two channels
        avg_db = float((float(rms[0]) + float(rms[1])) / 2.0)
        peak_db = float(max(float(peak[0]), float(peak[1])))

        # continuous LED count and integer part + fractional part for last LED brightness
        leds_float = self._db_to_leds_float(avg_db)
        leds_full = int(math.floor(leds_float))
        frac = max(0.0, min(1.0, leds_float - leds_full))
        # peak position (continuous -> we will map to an index)
        peak_pos = self._db_to_leds_float(peak_db)
        # clamp counts
        leds_full = max(0, min(self.num_leds, leds_full))

        # If rpi_ws281x not available, skip actual LED ops
        if self._strip is None:
            return

        # clear all
        self._clear_strip()

        # set peak marker (blue) overriding the color at that LED
        # Only display peak if it's above _min_db
        peak_idx = None
        if peak_db > self._min_db:
            # map continuous peak_pos to index: if at or above max -> last LED
            if peak_pos >= self.num_leds:
                peak_idx = self.num_leds - 1
            else:
                peak_idx = int(math.floor(peak_pos))  # floor to LED index
            peak_idx = max(0, min(self.num_leds - 1, peak_idx))

        if peak_idx is not None:
            self._set_pixel(peak_idx, (0, 0, 128))
        
        # set lit LEDs according to level
        if self._end_colors:
            # color by position so that starting LEDs are green and only last LEDs become yellow/red
            one_eighth_leds = max(1, int(math.ceil(self.num_leds / 8.0)))
            red_start = self.num_leds - one_eighth_leds
            yellow_start = max(0, self.num_leds - (2 * one_eighth_leds))

            # full LEDs
            for i in range(leds_full):
                if i >= red_start:
                    color = (255, 0, 0)
                elif i >= yellow_start:
                    color = (255, 255, 0)
                else:
                    color = (0, 255, 0)
                self._set_pixel(i, color)

            # fractional last LED (if any)
            if frac > 0.0 and leds_full < self.num_leds:
                i = leds_full
                if i >= red_start:
                    base = (255, 0, 0)
                elif i >= yellow_start:
                    base = (255, 255, 0)
                else:
                    base = (0, 255, 0)
                scaled = (int(base[0] * frac), int(base[1] * frac), int(base[2] * frac))
                self._set_pixel(i, scaled)
        else:
            # whole-bar coloring based on avg_db (color applies to full-lit LEDs;
            # last partial LED is scaled by frac)
            r_full, g_full, b_full = self._color_for_db(avg_db)
            for i in range(leds_full):
                self._set_pixel(i, (r_full, g_full, b_full))
            if frac > 0.0 and leds_full < self.num_leds:
                scaled = (int(r_full * frac), int(g_full * frac), int(b_full * frac))
                self._set_pixel(leds_full, scaled)

        # push to LED strip
        try:
            self._strip.show()
        except Exception:
            # ignore hardware errors silently
            pass
