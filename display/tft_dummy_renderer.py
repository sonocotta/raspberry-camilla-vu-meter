from typing import Optional
import traceback

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:
    Image = None  # type: ignore
    ImageDraw = None  # type: ignore
    ImageFont = None  # type: ignore


class TftDummyRenderer:
    """
    Simple TFT renderer that knows how to draw two-channel or mono text screens

    Constructor signature accepts the display device objects (device0, device1)
    and some optional layout parameters. Rendering is performed in `draw(rms_l, peak_l, rms_r, peak_r)`.

    The renderer will attempt to use Pillow to compose images and write them to device.display(img)
    or device.show(img). If Pillow or the device is unavailable it will fall back to console output.
    """

    def __init__(self, device0: Optional[object], device1: Optional[object], width: int = 320, height: int = 240, mono: bool = False):
        self.device0 = device0
        self.device1 = device1
        self.width = int(width)
        self.height = int(height)
        self.mono = bool(mono)

        self._font = None
        try:
            if ImageFont is not None:
                self._font = ImageFont.load_default()
        except Exception:
            self._font = None

    def _draw_text_on_image(self, label: str, rms: float, peak: float):
        if Image is None or ImageDraw is None:
            return None
        try:
            img = Image.new("RGB", (self.width, self.height), "black")
            draw = ImageDraw.Draw(img)
            font = self._font
            if font is None:
                draw.text((10, 10), f"{label}", fill="white")
                draw.text((10, 40), f"RMS: {rms:.1f} dB", fill="white")
                draw.text((10, 70), f"PK : {peak:.1f} dB", fill="white")
            else:
                draw.text((10, 8), f"{label}", fill="white", font=font)
                draw.text((10, 36), f"RMS: {rms:.1f} dB", fill="white", font=font)
                draw.text((10, 56), f"PK : {peak:.1f} dB", fill="white", font=font)
            return img
        except Exception:
            traceback.print_exc()
            return None

    def _push_image_to_device(self, dev, img, label: str, rms: float, peak: float):
        if img is None or dev is None:
            # fallback to console
            try:
                print(f"{label} RMS:{rms:.1f} dB  PK:{peak:.1f} dB")
            except Exception:
                traceback.print_exc()
            return
        try:
            if hasattr(dev, "display") and callable(getattr(dev, "display")):
                dev.display(img)
            elif hasattr(dev, "show") and callable(getattr(dev, "show")):
                dev.show(img)
            else:
                # try display and fallback to console
                try:
                    dev.display(img)
                except Exception:
                    print(f"{label} RMS:{rms:.1f} dB  PK:{peak:.1f} dB")
        except Exception:
            traceback.print_exc()
            try:
                print(f"{label} RMS:{rms:.1f} dB  PK:{peak:.1f} dB")
            except Exception:
                pass

    def draw(self, rms_l: float, peak_l: float, rms_r: float, peak_r: float):
        """
        Draw two channels. The renderer will handle mono mode if configured during construction.

        Parameters order: rms_l, peak_l, rms_r, peak_r
        """
        try:
            if self.mono:
                avg_rms = (float(rms_l) + float(rms_r)) / 2.0
                avg_peak = (float(peak_l) + float(peak_r)) / 2.0
                img = self._draw_text_on_image("LR", avg_rms, avg_peak)
                self._push_image_to_device(self.device0, img, "LR", avg_rms, avg_peak)
            else:
                # left channel
                img_l = self._draw_text_on_image("L", float(rms_l), float(peak_l))
                self._push_image_to_device(self.device0, img_l, "L", float(rms_l), float(peak_l))
                # right channel
                img_r = self._draw_text_on_image("R", float(rms_r), float(peak_r))
                self._push_image_to_device(self.device1, img_r, "R", float(rms_r), float(peak_r))
        except Exception:
            traceback.print_exc()

    def close(self):
        # renderer has no resources beyond what tft_display manages; present for symmetry
        return
