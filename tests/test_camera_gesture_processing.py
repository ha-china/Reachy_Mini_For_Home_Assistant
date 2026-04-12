import threading
import unittest
from types import SimpleNamespace

from reachy_mini_home_assistant.vision.camera_processing import process_gesture_detection


class _FakeGestureValue:
    def __init__(self, value: str):
        self.value = value


class _FakeGestureDetector:
    def __init__(self, value: str, confidence: float):
        self._value = value
        self._confidence = confidence

    def detect(self, _frame):
        return _FakeGestureValue(self._value), self._confidence


class CameraGestureProcessingTests(unittest.TestCase):
    def test_process_gesture_detection_updates_state_and_callbacks(self):
        state_updates = []
        server = SimpleNamespace(
            _gesture_detector=_FakeGestureDetector("peace", 0.91),
            _gesture_lock=threading.Lock(),
            _current_gesture="none",
            _gesture_confidence=0.0,
            _gesture_state_callback=lambda: state_updates.append("state"),
        )

        process_gesture_detection(server, frame=None)

        self.assertEqual(server._current_gesture, "peace")
        self.assertAlmostEqual(server._gesture_confidence, 0.91)
        self.assertEqual(state_updates, ["state"])

    def test_process_gesture_detection_clears_state_for_no_gesture(self):
        state_updates = []
        server = SimpleNamespace(
            _gesture_detector=_FakeGestureDetector("no_gesture", 0.0),
            _gesture_lock=threading.Lock(),
            _current_gesture="call",
            _gesture_confidence=0.72,
            _gesture_state_callback=lambda: state_updates.append("state"),
        )

        process_gesture_detection(server, frame=None)

        self.assertEqual(server._current_gesture, "none")
        self.assertEqual(server._gesture_confidence, 0.0)
        self.assertEqual(state_updates, ["state"])
