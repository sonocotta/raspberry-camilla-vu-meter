class DummyDisplay:
    def update(self, levels):
        """
        Display levels to console.
        Levels is typically a dict like:
        {
            'in': [levelL, levelR],
            'out': [levelL, levelR],
        }
        """
        in_levels = levels.capture_rms()
        in_peaks = levels.capture_peak()
        out_levels = levels.playback_rms()
        out_peaks = levels.playback_peak()

        print(f"Input: {in_levels}, peaks: {in_peaks} | Output: {out_levels}, peaks: {out_peaks}")