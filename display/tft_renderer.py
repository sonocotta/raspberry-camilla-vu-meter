from typing import Optional
import traceback
import math

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:
    Image = None  # type: ignore
    ImageDraw = None  # type: ignore
    ImageFont = None  # type: ignore


class TftRenderer:
    """Analog-style renderer that draws a horizontal scale and an arrow needle.

    Constructor signature is flexible: preferred
        __init__(device0, device1, width=320, height=240, mono=False, **kwargs)
    Accepts kwargs for configurable parameters (min_db, max_db, arrow_color, arrow_width,
    arrow_length, arrow_offset, bar_thickness, tick_height).
    """

    # Color constants (RGB tuples) — adjust here to change theme
    COLOR_BG = (0, 0, 0)              # Background
    COLOR_SCALE = (255, 255, 255)     # Scale lines and ticks
    COLOR_TEXT = (255, 255, 255)      # Labels/text
    COLOR_NEEDLE = (255, 128, 255)      # Needle (pink/magenta)
    COLOR_LED_GREEN = (0, 255, 0)     # LED bar below -12 dB
    COLOR_LED_YELLOW = (0, 255, 255)  # LED bar between -12 dB and 0 dB
    COLOR_LED_RED = (32, 32, 255)       # LED bar above 0 dB
    COLOR_LABEL_BORDER = (128, 128, 128)  # Border around channel labels

    def __init__(
        self,
        device0=None,
        device1=None,
        width: int = 320,
        height: int = 240,
        mono: bool = False,
        min_db: float = -72.0,
        max_db: float = 12.0,
        needle_color: str = 'white',
        needle_width: int = 1,
        needle_length: int = 280,
        needle_base_offset: int = 20,
        arrow_offset: int = 8,
        bar_thickness: int = 12,
        tick_height: int = 8,
        angle_span_deg: float = 60.0,
    ):
        self.device0 = device0
        self.device1 = device1
        self.width = int(width)
        self.height = int(height)
        self.mono = bool(mono)
        # configurable parameters with sensible defaults
        self._min_db = float(min_db)
        self._max_db = float(max_db)
        self._span_db = self._max_db - self._min_db
        # needle (arrow) parameters
        self.needle_color = needle_color
        self.needle_width = int(needle_width)
        self.needle_length = int(needle_length)
        self.needle_base_offset = int(needle_base_offset)
        # horizontal padding for scale
        self.arrow_offset = int(arrow_offset)
        self.bar_thickness = int(bar_thickness)
        self.tick_height = int(tick_height)
        # angle span centered at 0 (so angles go from -angle_span/2 .. +angle_span/2)
        self.angle_span_deg = float(angle_span_deg)
        # fonts
        # load fonts: default and a larger truetype if available
        try:
            if ImageFont is not None:
                self._font = ImageFont.load_default()
            else:
                self._font = None
        except Exception:
            self._font = None

        # try to load a larger truetype font for the big L/R; fallback to default
        try:
            if ImageFont is not None:
                # common path and generic font name; if not available fallback to default
                try:
                    self._big_font = ImageFont.truetype("DejaVuSans.ttf", 48)
                except Exception:
                    try:
                        self._big_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 48)
                    except Exception:
                        self._big_font = self._font
            else:
                self._big_font = self._font
        except Exception:
            self._big_font = self._font

    def _value_to_x(self, value: float) -> int:
        left = self.arrow_offset
        length = max(1, self.width - 2 * self.arrow_offset)
        try:
            t = (float(value) - self._min_db) / (self._max_db - self._min_db)
        except Exception:
            t = 0.0
        t = max(0.0, min(1.0, t))
        return int(left + t * length)

    def _push_image_to_device(self, dev, img):
        if img is None or dev is None:
            return
        dev.display(img)

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
    
    def _draw_scale(self, draw, left: int, right: int, center_y: int):
        """Draw radial scale: arc boundaries, radial ticks every 12 dB, and dB labels."""
        # Dial geometry aligned with needle pivot and length
        cx = self.width // 2
        cy = self.height + int(self.needle_length * 0.2)
        r_outer = self.needle_length
        r_inner = max(1, r_outer - self.bar_thickness)
        tick_len = self.tick_height
        long_tick_len = tick_len * 2
        half_span = self.angle_span_deg / 2.0
        start_deg = 270.0 - half_span
        end_deg = 270.0 + half_span

        # Draw arc boundaries (inner and outer)
        try:
            bbox_outer = (cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer)
            bbox_inner = (cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner)
            draw.arc(bbox_outer, start=start_deg, end=end_deg, fill=self.COLOR_SCALE, width=1)
            draw.arc(bbox_inner, start=start_deg, end=end_deg, fill=self.COLOR_SCALE, width=1)
        except Exception:
            # Fallback: approximate arcs with short chords
            steps = 64
            for i in range(steps):
                a0 = math.radians(-half_span + (i/steps)*self.angle_span_deg)
                a1 = math.radians(-half_span + ((i+1)/steps)*self.angle_span_deg)
                x0o = int(cx + r_outer * math.sin(a0)); y0o = int(cy - r_outer * math.cos(a0))
                x1o = int(cx + r_outer * math.sin(a1)); y1o = int(cy - r_outer * math.cos(a1))
                x0i = int(cx + r_inner * math.sin(a0)); y0i = int(cy - r_inner * math.cos(a0))
                x1i = int(cx + r_inner * math.sin(a1)); y1i = int(cy - r_inner * math.cos(a1))
                draw.line((x0o, y0o, x1o, y1o), fill=self.COLOR_SCALE)
                draw.line((x0i, y0i, x1i, y1i), fill=self.COLOR_SCALE)

        # ticks every 12 dB, including 0
        start_db = int(self._min_db // 12 * 12)
        end_db = int((self._max_db + 11) // 12 * 12)
        for v in range(start_db, end_db + 1, 12):
            if v < self._min_db or v > self._max_db:
                continue
            tick_color = self._color_for_db(v)
            a = self._db_to_angle(v)
            # radial tick from arc outward
            r0 = r_outer
            r1 = r_outer + (long_tick_len if v == 0 else tick_len)
            x0 = int(cx + r0 * math.sin(a)); y0 = int(cy - r0 * math.cos(a))
            x1 = int(cx + r1 * math.sin(a)); y1 = int(cy - r1 * math.cos(a))
            draw.line((x0, y0, x1, y1), fill=tick_color)

            # label outside the tick
            try:
                if self._font is not None:
                    label = f"{v}"
                    tx_w, tx_h = self._text_size(draw, label, self._font)
                    r_text = r1 + 6
                    tx = int(cx + r_text * math.sin(a) - tx_w/2)
                    ty = int(cy - r_text * math.cos(a) - tx_h/2)
                    draw.text((tx, ty), label, fill=tick_color, font=self._font)
            except Exception:
                pass

        # Draw percentage ticks and labels under the scale (toward center)
        try:
            self._draw_percentage_scale_radial(draw)
        except Exception:
            pass

    def _draw_percentage_scale_radial(self, draw):
        """Draw percentage ticks/labels along the inner side of the arc (under the scale)."""
        if self._font is None:
            return
        # Geometry (match _draw_scale)
        cx = self.width // 2
        cy = self.height + int(self.needle_length * 0.2)
        r_outer = self.needle_length
        r_inner = max(1, r_outer - self.bar_thickness)
        inner_tick_len = max(4, self.tick_height // 2)

        percentage_points = []
        # Above 0 dB prominent marks
        for percent in [100, 200, 300, 400]:
            db_value = 20.0 * math.log10(percent / 100.0)
            if self._min_db <= db_value <= self._max_db:
                percentage_points.append((percent, db_value, percent in [100]))

        # Below 0 dB: 10% steps to 10%
        for percent in [90, 80, 70, 60, 50, 40, 30, 20, 10]:
            db_value = 20.0 * math.log10(percent / 100.0)
            if self._min_db <= db_value <= self._max_db:
                percentage_points.append((percent, db_value, percent == 10))

        # 1% steps to 1%
        for percent in [9, 8, 7, 6, 5, 4, 3, 2, 1]:
            db_value = 20.0 * math.log10(percent / 100.0)
            if self._min_db <= db_value <= self._max_db:
                percentage_points.append((percent, db_value, percent == 1))

        # 0.1% steps to 0.1%
        for i in range(9, 0, -1):
            percent = i / 10.0
            db_value = 20.0 * math.log10(percent / 100.0)
            if self._min_db <= db_value <= self._max_db:
                percentage_points.append((percent, db_value, percent == 0.1))

        # Optional: include 0.01% range if within span (commented to avoid crowding)
        # for i in range(9, 0, -1):
        #     percent = i / 100.0
        #     db_value = 20.0 * math.log10(percent / 100.0)
        #     if self._min_db <= db_value <= self._max_db:
        #         percentage_points.append((percent, db_value, percent == 0.01))

        percentage_points.sort(key=lambda x: x[1])
        if not percentage_points:
            return
        min_percent = percentage_points[0][0]
        max_percent = percentage_points[-1][0]

        for percent, db_value, show_text_label in percentage_points:
            a = self._db_to_angle(db_value)
            tick_color = self._color_for_db(db_value)
            r0 = r_inner
            r1 = max(1, r_inner - inner_tick_len)
            x0 = int(cx + r0 * math.sin(a)); y0 = int(cy - r0 * math.cos(a))
            x1 = int(cx + r1 * math.sin(a)); y1 = int(cy - r1 * math.cos(a))
            draw.line((x0, y0, x1, y1), fill=tick_color)

            show_label = (show_text_label or percent == min_percent or percent == max_percent or percent == 100)
            if show_label:
                # Format label matching earlier scheme
                if percent >= 1:
                    label = f"{int(percent)}"
                elif percent >= 0.01:
                    label = f"{percent:.1f}"
                else:
                    label = f"{percent:.2f}"
                # Place label slightly further inward
                r_text = max(1, r1 - 6)
                tw, th = self._text_size(draw, label, self._font)
                tx = int(cx + r_text * math.sin(a) - tw/2)
                ty = int(cy - r_text * math.cos(a) - th/2)
                draw.text((tx, ty), label, fill=tick_color, font=self._font)

    def _draw_percentage_scale(self, draw, left: int, right: int, center_y: int, top_y: int):
        """Draw percentage labels and tick marks above the scale bar"""
        try:
            if self._font is None:
                return
                
            # Define percentage to dB mapping: 0 dB = 100%
            # Using proper logarithmic calculation: dB = 20 * log10(amplitude_ratio)
            percentage_points = []
            
            # Above 0 dB: 100%, 200%, 300%, 400%
            above_zero_percentages = [100, 200, 300, 400]
            for percent in above_zero_percentages:
                db_value = 20.0 * math.log10(percent / 100.0)
                if self._min_db <= db_value <= self._max_db:
                    percentage_points.append((percent, db_value, percent in [100]))
            
            # Below 0 dB: logarithmic steps
            # 10% steps: 90%, 80%, 70%, 60%, 50%, 40%, 30%, 20%, 10%
            for percent in [90, 80, 70, 60, 50, 40, 30, 20, 10]:
                db_value = 20.0 * math.log10(percent / 100.0)
                if self._min_db <= db_value <= self._max_db:
                    percentage_points.append((percent, db_value, percent == 10))
            
            # 1% steps: 9%, 8%, 7%, 6%, 5%, 4%, 3%, 2%, 1%
            for percent in [9, 8, 7, 6, 5, 4, 3, 2, 1]:
                db_value = 20.0 * math.log10(percent / 100.0)
                if self._min_db <= db_value <= self._max_db:
                    percentage_points.append((percent, db_value, percent == 1))
            
            # 0.1% steps: 0.9%, 0.8%, ..., 0.1%
            for i in range(9, 0, -1):
                percent = i / 10.0
                db_value = 20.0 * math.log10(percent / 100.0)
                if self._min_db <= db_value <= self._max_db:
                    percentage_points.append((percent, db_value, percent == 0.1))
            
            # # 0.01% steps: 0.09%, 0.08%, ..., 0.01%
            # for i in range(9, 0, -1):
            #     percent = i / 100.0
            #     db_value = 20.0 * math.log10(percent / 100.0)
            #     if self._min_db <= db_value <= self._max_db:
            #         percentage_points.append((percent, db_value, percent == 0.01))
            
            # Sort by dB value
            percentage_points.sort(key=lambda x: x[1])
            
            # Find min and max values for boundary labels
            min_percent = percentage_points[0][0] if percentage_points else None
            max_percent = percentage_points[-1][0] if percentage_points else None
            
            # Draw percentage tick marks and labels
            for percent, db_value, show_text_label in percentage_points:
                x = self._value_to_x(db_value)
                
                # Draw tick mark above the scale
                tick_top = top_y - self.tick_height // 2
                tick_bottom = top_y
                tick_color = self._color_for_db(db_value)
                draw.line((x, tick_top, x, tick_bottom), fill=tick_color)
                
                # Emphasize 100% mark
                if percent == 100:
                    draw.line((x, tick_top - self.tick_height // 2, x, tick_bottom), fill=tick_color)
                
                # Draw text labels only for specific percentages and boundaries
                show_label = (show_text_label or 
                             percent == min_percent or 
                             percent == max_percent or
                             percent == 100)
                
                if show_label:
                    if percent >= 1:
                        label = f"{int(percent)}"
                    elif percent >= 0.01:
                        label = f"{percent:.1f}"
                    else:
                        label = f"{percent:.2f}"
                    
                    text_w, text_h = self._text_size(draw, label, self._font)
                    text_x = x - text_w // 2
                    text_y = tick_top - text_h - 2
                    draw.text((text_x, text_y), label, fill=tick_color, font=self._font)
                
        except Exception:
            pass

    def _draw_filled_bar(self, draw, left: int, center_y: int, peak_value: float):
        """Draw LED-style radial bar: small colored arc segments with ~1px gaps."""
        # Dial geometry aligned with needle
        cx = self.width // 2
        cy = self.height + int(self.needle_length * 0.2)
        r_outer = self.needle_length
        r_inner = max(1, r_outer - self.bar_thickness)
        half_span = self.angle_span_deg / 2.0

        # Angle range
        a_min = math.radians(-half_span)
        a_max = math.radians(half_span)
        a_peak = self._db_to_angle(peak_value)
        a_end = max(a_min, min(a_peak, a_max))
        if a_end <= a_min:
            return

        # Segment sizing: approximate square LEDs along arc
        led_size = max(2, r_outer - r_inner)  # arc length ~= radial thickness
        gap = 1  # ~1px gap along arc
        r_mid = (r_inner + r_outer) / 2.0
        dtheta_led = led_size / max(1.0, r_mid)
        dtheta_step = (led_size + gap) / max(1.0, r_mid)

        a = a_min
        while a < a_end:
            a2 = min(a + dtheta_led, a_end)
            # Color based on dB at segment center
            ac = (a + a2) * 0.5
            db_here = self._angle_to_db(ac)
            color = self._color_for_db(db_here)

            # Build ring-segment polygon (inner/outer between angles a..a2)
            x1o = int(cx + r_outer * math.sin(a));  y1o = int(cy - r_outer * math.cos(a))
            x2o = int(cx + r_outer * math.sin(a2)); y2o = int(cy - r_outer * math.cos(a2))
            x2i = int(cx + r_inner * math.sin(a2)); y2i = int(cy - r_inner * math.cos(a2))
            x1i = int(cx + r_inner * math.sin(a));  y1i = int(cy - r_inner * math.cos(a))
            draw.polygon([(x1o, y1o), (x2o, y2o), (x2i, y2i), (x1i, y1i)], fill=color)

            a += dtheta_step
    
    def _x_to_value(self, x: int) -> float:
        """Convert x coordinate back to dB value"""
        left = self.arrow_offset
        length = max(1, self.width - 2 * self.arrow_offset)
        try:
            t = (x - left) / length
            t = max(0.0, min(1.0, t))
            return self._min_db + t * (self._max_db - self._min_db)
        except Exception:
            return self._min_db

    def _angle_to_db(self, angle_rad: float) -> float:
        """Inverse of _db_to_angle: map angle back to dB."""
        half_span = self.angle_span_deg / 2.0
        angle_deg = math.degrees(angle_rad)
        # our 0 deg is vertical down; already consistent with _db_to_angle
        ratio = (angle_deg + half_span) / self.angle_span_deg
        ratio = max(0.0, min(1.0, ratio))
        return self._min_db + ratio * self._span_db

    def _color_for_db(self, db_value: float):
        """Return LED color for a given dB value based on thresholds."""
        try:
            v = float(db_value)
        except Exception:
            v = self._min_db
        if v >= 0.0:
            return self.COLOR_LED_RED
        if v >= -12.0:
            return self.COLOR_LED_YELLOW
        return self.COLOR_LED_GREEN

    def _draw_channel_indicator(self, draw, center_x: int, center_y: int, label: str):
        big_font = self._big_font or self._font
        text_w, text_h = self._text_size(draw, label, big_font)
        tx = center_x - text_w // 2
        ty = center_y - text_h // 2
        # Draw a thin border around the channel label
        pad = 6
        bx0 = tx - pad
        by0 = ty + pad
        bx1 = tx + text_w + pad
        by1 = ty + text_h + 2 * pad
        try:
            # Pillow supports outline and width on rectangle in modern versions
            draw.rectangle((bx0, by0, bx1, by1), outline=self.COLOR_LABEL_BORDER, width=1)
        except Exception:
            # Fallback: draw rectangle with lines
            draw.line((bx0, by0, bx1, by0), fill=self.COLOR_LABEL_BORDER)
            draw.line((bx1, by0, bx1, by1), fill=self.COLOR_LABEL_BORDER)
            draw.line((bx1, by1, bx0, by1), fill=self.COLOR_LABEL_BORDER)
            draw.line((bx0, by1, bx0, by0), fill=self.COLOR_LABEL_BORDER)
        draw.text((tx, ty), label, fill=self.COLOR_LABEL_BORDER, font=self._big_font)

    def _clamp(self, v: float, lo: float, hi: float) -> float:
        return lo if v < lo else (hi if v > hi else v)
    
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
    
    def _draw_needle(self, draw, rms: float):
        """
        Draw a single needle meter on the provided draw object.
        - pivot is above the visible area at (cx, pivot_y)
        - needle length is self.needle_length
        """
        cx = self.width // 2
        # pivot above the screen: place it so needle originates outside and can sweep into view
        pivot_y = self.height + int(self.needle_length * 0.2)

        # compute angle and endpoint
        angle = self._db_to_angle(rms)
        # angle 0 points downwards; we use angle measured from vertical
        # compute endpoint
        ex = int(cx + self.needle_length * math.sin(angle))
        ey = int(pivot_y - self.needle_length * math.cos(angle))

        # draw a 2px wide needle in configured color
            # Draw the main line
        draw.line([(cx, pivot_y), (ex, ey)], fill=self.COLOR_NEEDLE)
            # Draw offset lines to create 2px width
        draw.line([(cx+1, pivot_y), (ex+1, ey)], fill=self.COLOR_NEEDLE)
        draw.line([(cx, pivot_y+1), (ex, ey+1)], fill=self.COLOR_NEEDLE)
        draw.line([(cx+1, pivot_y+1), (ex+1, ey+1)], fill=self.COLOR_NEEDLE)

    def draw(self, rms_l: float, peak_l: float, rms_r: float, peak_r: float):
        try:
            if self.mono:
                avg_rms = (float(rms_l) + float(rms_r)) / 2.0
                avg_peak = (float(peak_l) + float(peak_r)) / 2.0
                img = None
                if Image is not None:
                    img = Image.new('RGB', (self.width, self.height), self.COLOR_BG)
                    draw = ImageDraw.Draw(img)
                    left = self.arrow_offset
                    right = self.width - self.arrow_offset
                    center_y = self.height // 6
                    self._draw_scale(draw, left, right, center_y)
                    self._draw_filled_bar(draw, left, center_y, avg_peak)
                    self._draw_needle(draw, float(avg_rms))
                    self._draw_channel_indicator(draw, self.width // 2, 2 * self.height // 3, "LR")
                if img is None or self.device0 is None:
                    print(f"LR RMS:{avg_rms:.1f} dB  PK:{avg_peak:.1f} dB")
                else:
                    self._push_image_to_device(self.device0, img)
            else:
                # left channel image
                img_l = None
                if Image is not None:
                    img_l = Image.new('RGB', (self.width, self.height), self.COLOR_BG)
                    draw_l = ImageDraw.Draw(img_l)
                    left = self.arrow_offset
                    right = self.width - self.arrow_offset
                    center_y = self.height // 6
                    self._draw_scale(draw_l, left, right, center_y)
                    self._draw_filled_bar(draw_l, left, center_y, float(peak_l))
                    self._draw_needle(draw_l, float(rms_l))
                    # large channel label for left
                    try:
                        self._draw_channel_indicator(draw_l, self.width // 2, 2 * self.height // 3, "L")
                    except Exception:
                        pass

                # right channel image
                img_r = None
                if Image is not None:
                    img_r = Image.new('RGB', (self.width, self.height), self.COLOR_BG)
                    draw_r = ImageDraw.Draw(img_r)
                    left = self.arrow_offset
                    right = self.width - self.arrow_offset
                    center_y = self.height // 6
                    self._draw_scale(draw_r, left, right, center_y)
                    self._draw_filled_bar(draw_r, left, center_y, float(peak_r))
                    self._draw_needle(draw_r, float(rms_r))
                    self._draw_channel_indicator(draw_r, self.width // 2, 2 * self.height // 3, "R")

                if img_l is None or self.device0 is None:
                    print(f"L RMS:{float(rms_l):.1f} dB  PK:{float(peak_l):.1f} dB")
                else:
                    self._push_image_to_device(self.device0, img_l)

                if img_r is None or self.device1 is None:
                    print(f"R RMS:{float(rms_r):.1f} dB  PK:{float(peak_r):.1f} dB")
                else:
                    self._push_image_to_device(self.device1, img_r)
        except Exception:
            traceback.print_exc()

    def close(self):
        """No special cleanup needed for this renderer."""
        pass