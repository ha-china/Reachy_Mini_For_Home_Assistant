from __future__ import annotations

import time

import numpy as np

from .audio_player_shared import MOVEMENT_LATENCY_S, SWAY_FRAME_DT_S


class AudioPlayerWobbleMixin:
    def _new_sway_analyzer(self):
        try:
            from ..motion.speech_sway import SpeechSwayRT

            return SpeechSwayRT()
        except Exception:
            return None

    def _compute_sway_frames(self, analyzer, pcm: np.ndarray, sample_rate: int) -> list[dict]:
        if analyzer is None:
            return []
        try:
            return analyzer.feed(pcm, sample_rate) or []
        except Exception:
            return []

    def _reset_sway_output(self) -> None:
        if self._sway_callback is None:
            return
        try:
            self._sway_callback({"pitch_rad": 0.0, "yaw_rad": 0.0, "roll_rad": 0.0, "x_m": 0.0, "y_m": 0.0, "z_m": 0.0})
        except Exception:
            pass

    def _init_stream_sway_context(self) -> dict | None:
        if self._sway_callback is None:
            return None
        analyzer = self._new_sway_analyzer()
        if analyzer is None:
            return None
        return {"sway": analyzer, "base_ts": time.monotonic(), "frames_done": 0}

    def _feed_stream_sway(self, ctx: dict | None, pcm: np.ndarray, sample_rate: int) -> None:
        if ctx is None or self._sway_callback is None:
            return
        try:
            results = self._compute_sway_frames(ctx["sway"], pcm, sample_rate)
            if not results:
                return
            base_ts = float(ctx["base_ts"])
            for item in results:
                target = base_ts + MOVEMENT_LATENCY_S + ctx["frames_done"] * SWAY_FRAME_DT_S
                now = time.monotonic()
                if target > now:
                    time.sleep(min(0.02, target - now))
                self._sway_callback(item)
                ctx["frames_done"] += 1
        except Exception:
            pass

    def _finalize_stream_sway(self, ctx: dict | None) -> None:
        if ctx is None or self._sway_callback is None:
            return
        self._reset_sway_output()
