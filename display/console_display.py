from typing import Dict, List, Optional


class ConsoleDisplay:
    """
    Console pseudo-graphical VU display.

    - Shows 2 bars (one per channel).
    - Bar length is configurable (default 40).
    - Values are mapped to the log dB range [-120 .. 12].
    - Peak is shown as the '|' symbol at the peak position.
    - Each update overwrites the previous two lines instead of adding new lines.
    """

    def __init__(self, bar_length: int = 40):
        self.bar_length = max(1, int(bar_length))
        self._first_draw = True
        self._lines = 2  # we display two lines (two channels)

    def _clamp(self, v: float, lo: float, hi: float) -> float:
        return lo if v < lo else (hi if v > hi else v)

    def _db_to_pos(self, db: float) -> int:
        # Map dB in [-120, 12] to [0, bar_length]
        min_db = -120.0
        max_db = 12.0
        db = self._clamp(db, min_db, max_db)
        span = max_db - min_db
        ratio = (db - min_db) / span
        return int(round(ratio * self.bar_length))

    def _prepare_levels(self, levels) -> Optional[Dict[str, List[float]]]:
        """
        Accept either:
        - a dict returned by CamillaDSP Levels.levels() (keys playback_rms/playback_peak/etc)
        - an object exposing a callable .levels() method that returns such a dict
        """
        if not levels:
            return None

        if isinstance(levels, dict):
            return levels

        # try to call .levels() if present
        try:
            if hasattr(levels, "levels") and callable(levels.levels):
                return levels.levels()
        except Exception:
            pass

        # unknown format
        return None

    def update(self, levels):
        """
        levels: dict as returned by Levels.levels()
        Example:
        {
          "playback_rms": [ -20.0, -22.5 ],
          "playback_peak": [ -10.0, -12.0 ],
          ...
        }
        """
        data = self._prepare_levels(levels)
        if not data:
            return

        playback_rms = data.get("playback_rms") or data.get("capture_rms") or []
        playback_peak = data.get("playback_peak") or data.get("capture_peak") or []

        # Ensure we at least render two channels (pad with -120 dB if missing)
        while len(playback_rms) < 2:
            playback_rms.append(-120.0)
        while len(playback_peak) < 2:
            playback_peak.append(-120.0)

        lines: List[str] = []
        for ch_index in range(2):
            value_db = float(playback_rms[ch_index])
            peak_db = float(playback_peak[ch_index])

            fill_pos = self._db_to_pos(value_db)
            peak_pos = self._db_to_pos(peak_db)

            # build bar
            filled = "█" * fill_pos
            empty = " " * (self.bar_length - fill_pos)
            bar_chars = list(filled + empty)

            # place peak marker (clamp within range)
            pk = max(0, min(self.bar_length - 1, peak_pos))
            bar_chars[pk] = "|"

            bar = "".join(bar_chars)

            # label: channel number, bar, and numeric dB value
            line = f"Ch{ch_index+1:1d} [{bar}] {value_db:6.1f} dB"
            lines.append(line)

        # Overwrite previous output instead of printing new lines
        if not self._first_draw:
            # move cursor up N lines to overwrite them
            print(f"\x1b[{self._lines}A", end="")

        # print/replace each line (clearing it first)
        for ln in lines:
            # clear the current line and print
            print("\x1b[2K" + ln)

        # ensure next update will overwrite
        self._first_draw = False