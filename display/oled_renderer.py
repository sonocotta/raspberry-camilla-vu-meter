import math
from typing import Optional

try:
    from PIL import ImageFont  # type: ignore
except Exception:
    ImageFont = None  # type: ignore


class OledRenderer:
    """Rendering logic for SH1106 OLED using a provided draw context.

    This class mirrors the responsibilities of the TFT renderer, but targets
    monochrome OLED rendering via the luma canvas draw API passed in.
    """

    def __init__(
        self,
        width: int = 128,
        height: int = 64,
        min_db: float = -72.0,
        max_db: float = 12.0,
        needle_length: int = 80,
        angle_span_deg: float = 120.0,
    ) -> None:
        self.width = int(width)
        self.height = int(height)
        self._min_db = float(min_db)
        self._max_db = float(max_db)
        if self._max_db <= self._min_db:
            self._min_db = -72.0
            self._max_db = 12.0
        self._span_db = self._max_db - self._min_db
        self.needle_length = max(1, int(needle_length))
        self.angle_span_deg = float(angle_span_deg)

        # fonts
        try:
            self._font = ImageFont.load_default() if ImageFont else None
        except Exception:
            self._font = None
        try:
            self._big_font = ImageFont.truetype("DejaVuSans.ttf", 24) if ImageFont else None
        except Exception:
            try:
                self._big_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24) if ImageFont else None
            except Exception:
                self._big_font = self._font
        try:
            self._small_font = ImageFont.truetype("DejaVuSans.ttf", 7) if ImageFont else None
        except Exception:
            try:
                self._small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 7) if ImageFont else None
            except Exception:
                self._small_font = self._font

    def _clamp(self, v: float, lo: float, hi: float) -> float:
        return lo if v < lo else (hi if v > hi else v)

    def _text_size(self, draw, text: str, font):
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            return (bbox[2] - bbox[0], bbox[3] - bbox[1])
        except Exception:
            pass
        try:
            return draw.textsize(text, font=font)
        except Exception:
            pass
        try:
            bbox = font.getbbox(text)
            return (bbox[2] - bbox[0], bbox[3] - bbox[1])
        except Exception:
            pass
        try:
            return font.getsize(text)
        except Exception:
            pass
        return (len(text) * 6, 8)

    def _db_to_angle(self, db: float) -> float:
        db = float(db)
        db = self._clamp(db, self._min_db, self._max_db)
        ratio = (db - self._min_db) / self._span_db
        half_span = self.angle_span_deg / 2.0
        angle_deg = (ratio * self.angle_span_deg) - half_span
        return math.radians(angle_deg)

    def _db_to_x(self, db: float, left: int, right: int) -> int:
        db = float(db)
        db = self._clamp(db, self._min_db, self._max_db)
        ratio = (db - self._min_db) / self._span_db
        return int(round(left + ratio * (right - left)))

    def _percent_to_db(self, percent: float) -> float:
        """Convert amplitude percentage to dB. 100% -> 0 dB; 200% -> +6.02 dB; 1% -> -40 dB."""
        if percent <= 0:
            return self._min_db
        return 20.0 * math.log10(percent / 100.0)

    def _draw_percentage_scale(self, draw, left: int, right: int, bar_top: int, bar_bottom: int):
        """
        Draw percentage ticks below the bar using logarithmic mapping.
        - Above 100%: ticks at 100%, 200%, 300%
        - Below 100%: 10% steps down to 10%, then 1% steps down to 1%
        Labels only for 1%, 10%, 100%.
        """
        label_percents = {1, 10, 100}

        percents = []
        percents.extend([100, 200, 300])
        percents.extend(list(range(90, 0, -10)))  # 90..10
        percents.extend(list(range(9, 0, -1)))    # 9..1

        tick_top = min(self.height - 1, bar_bottom + 1)
        tick_bottom_long = min(self.height - 1, bar_bottom + 4)
        tick_bottom_short = min(self.height - 1, bar_bottom + 3)

        for p in percents:
            db = self._percent_to_db(float(p))
            if db < self._min_db or db > self._max_db:
                continue
            x = self._db_to_x(db, left, right)
            is_label = p in label_percents
            draw.line((x, tick_top, x, (tick_bottom_long if is_label else tick_bottom_short)), fill="white")
            if is_label:
                txt = f"{p}"
                tw, th = self._text_size(draw, txt, self._small_font)
                tx = max(0, min(self.width - tw, x - (tw // 2)))
                ty = min(self.height - th, tick_bottom_long + 1)
                draw.text((tx, ty), txt, fill="white", font=self._small_font)

    def _draw_meter(self, draw, rms: float):
        cx = self.width // 2
        pivot_y = -int(self.needle_length * 0.2)
        angle = self._db_to_angle(rms)
        ex = int(cx + self.needle_length * math.sin(angle))
        ey = int(pivot_y + self.needle_length * math.cos(angle))
        draw.line([(cx, pivot_y), (ex, ey)], fill="white")

    def render(self, draw, label: str, rms: float, peak: float):
        # channel label
        big_font = self._big_font or self._font
        lw, lh = self._text_size(draw, label, big_font)
        lx = (self.width - lw) // 2
        ly = max(0, (self.height // 2) - (lh // 2) - 16)
        # border around label (thin rectangle)
        pad = 2
        bx0 = max(0, lx - pad)
        by0 = max(0, ly + pad)
        bx1 = min(self.width - 1, lx + lw + pad)
        by1 = min(self.height + 1, ly + lh + 2 * pad + 2)
        draw.rectangle((bx0, by0, bx1, by1), outline="white")
        draw.text((lx, ly), label, fill="white", font=big_font)

        # needle
        self._draw_meter(draw, rms)

        # bottom linear bar with ticks and labels
        left = 6
        right = self.width - 6
        bar_top = self.height - 14
        bar_bottom = self.height - 11

        # base bar
        draw.line((left, bar_top, right, bar_top), fill="white")
        draw.line((left, bar_bottom, right, bar_bottom), fill="white")

        def draw_tick(x, tall: bool = True):
            """Draw ticks only on the upper side of the scale (above the bar)."""
            if tall:
                # tall tick: from above down to the top line of the bar
                draw.line((x, bar_top - 3, x, bar_top), fill="white")
            else:
                # short tick: slightly shorter, still only above the bar
                draw.line((x, bar_top - 2, x, bar_top), fill="white")

        # min/max ticks + labels
        draw_tick(left)
        min_txt = f"{int(self._min_db)}"
        min_w, min_h = self._text_size(draw, min_txt, self._small_font)
        draw.text((left - (min_w // 2), bar_top - min_h - 4), min_txt, fill="white", font=self._small_font)

        draw_tick(right)
        max_txt = f"{int(self._max_db)}"
        max_w, max_h = self._text_size(draw, max_txt, self._small_font)
        draw.text((right - (max_w // 2), bar_top - max_h - 4), max_txt, fill="white", font=self._small_font)

        # 0 dB marker
        x0 = self._db_to_x(0.0, left, right)
        draw_tick(x0)
        z_txt = "0"
        z_w, z_h = self._text_size(draw, z_txt, self._small_font)
        draw.text((x0 - (z_w // 2), bar_top - z_h - 4), z_txt, fill="white", font=self._small_font)

        # additional step markers and labels for -12dB steps below 0dB
        step_db = -12
        i = 1
        while step_db >= self._min_db:
            xs = self._db_to_x(step_db, left, right)
            draw_tick(xs, tall=False)
            lbl = f"{int(step_db)}"
            lw, lh = self._text_size(draw, lbl, self._small_font)
            draw.text((xs - (lw // 2), bar_top - lh - 4), lbl, fill="white", font=self._small_font)
            step_db -= 12 * i

        # percentage ticks along the bottom side of the bar
        self._draw_percentage_scale(draw, left, right, bar_top, bar_bottom)

        # peak fill rectangle
        if peak > self._min_db:
            xp = self._db_to_x(peak, left, right)
            x_start = max(left, min(right, left))
            x_end = max(left, min(right, xp))
            if x_end >= x_start:
                draw.rectangle((x_start, bar_top + 1, x_end, bar_bottom - 1), outline="white", fill="white")
