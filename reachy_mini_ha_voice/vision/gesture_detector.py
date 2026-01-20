"""Gesture detection using HaGRID ONNX models."""

from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)


class Gesture(Enum):
    NONE = "no_gesture"
    CALL = "call"
    DISLIKE = "dislike"
    FIST = "fist"
    FOUR = "four"
    LIKE = "like"
    MUTE = "mute"
    OK = "ok"
    ONE = "one"
    PALM = "palm"
    PEACE = "peace"
    PEACE_INVERTED = "peace_inverted"
    ROCK = "rock"
    STOP = "stop"
    STOP_INVERTED = "stop_inverted"
    THREE = "three"
    THREE2 = "three2"
    TWO_UP = "two_up"
    TWO_UP_INVERTED = "two_up_inverted"


_GESTURE_CLASSES = [
    'hand_down', 'hand_right', 'hand_left', 'thumb_index', 'thumb_left',
    'thumb_right', 'thumb_down', 'half_up', 'half_left', 'half_right',
    'half_down', 'part_hand_heart', 'part_hand_heart2', 'fist_inverted',
    'two_left', 'two_right', 'two_down', 'grabbing', 'grip', 'point',
    'call', 'three3', 'little_finger', 'middle_finger', 'dislike', 'fist',
    'four', 'like', 'mute', 'ok', 'one', 'palm', 'peace', 'peace_inverted',
    'rock', 'stop', 'stop_inverted', 'three', 'three2', 'two_up',
    'two_up_inverted', 'three_gun', 'one_left', 'one_right', 'one_down'
]

_NAME_TO_GESTURE = {
    'call': Gesture.CALL, 'dislike': Gesture.DISLIKE, 'fist': Gesture.FIST,
    'four': Gesture.FOUR, 'like': Gesture.LIKE, 'mute': Gesture.MUTE,
    'ok': Gesture.OK, 'one': Gesture.ONE, 'palm': Gesture.PALM,
    'peace': Gesture.PEACE, 'peace_inverted': Gesture.PEACE_INVERTED,
    'rock': Gesture.ROCK, 'stop': Gesture.STOP,
    'stop_inverted': Gesture.STOP_INVERTED, 'three': Gesture.THREE,
    'three2': Gesture.THREE2, 'two_up': Gesture.TWO_UP,
    'two_up_inverted': Gesture.TWO_UP_INVERTED,
}


class GestureDetector:
    def __init__(self, confidence_threshold: float = 0.3, detection_threshold: float = 0.3):
        self._confidence_threshold = confidence_threshold
        self._detection_threshold = detection_threshold
        models_dir = Path(__file__).parent / "models"
        self._detector_path = models_dir / "hand_detector.onnx"
        self._classifier_path = models_dir / "crops_classifier.onnx"
        self._detector = None
        self._classifier = None
        self._available = False
        self._mean = np.array([127, 127, 127], dtype=np.float32)
        self._std = np.array([128, 128, 128], dtype=np.float32)
        self._detector_size = (320, 240)
        self._classifier_size = (128, 128)
        self._load_models()

    def _load_models(self) -> None:
        try:
            import onnxruntime as ort
        except ImportError:
            logger.warning("onnxruntime not installed")
            return
        if not self._detector_path.exists() or not self._classifier_path.exists():
            logger.warning("Model files not found")
            return
        try:
            providers = ['CPUExecutionProvider']
            logger.info("Loading gesture models...")
            self._detector = ort.InferenceSession(str(self._detector_path), providers=providers)
            self._classifier = ort.InferenceSession(str(self._classifier_path), providers=providers)
            self._det_input = self._detector.get_inputs()[0].name
            self._det_outputs = [o.name for o in self._detector.get_outputs()]
            self._cls_input = self._classifier.get_inputs()[0].name
            self._available = True
            logger.info("Gesture detection ready")
        except Exception as e:
            logger.error("Failed to load models: %s", e)

    @property
    def is_available(self) -> bool:
        return self._available

    def _preprocess(self, frame: NDArray, size: tuple[int, int]) -> NDArray:
        img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, size)
        img = (img.astype(np.float32) - self._mean) / self._std
        img = np.transpose(img, [2, 0, 1])
        return np.expand_dims(img, axis=0)

    def _detect_hand(self, frame: NDArray) -> tuple[int, int, int, int, float] | None:
        if self._detector is None:
            return None
        h, w = frame.shape[:2]
        inp = self._preprocess(frame, self._detector_size)
        outs = self._detector.run(self._det_outputs, {self._det_input: inp})
        boxes = outs[0]
        scores = outs[2]
        if len(boxes) == 0:
            return None
        best_i, best_c = -1, self._detection_threshold
        for i, c in enumerate(scores):
            if c > best_c:
                best_c, best_i = float(c), i
        if best_i < 0:
            return None
        b = boxes[best_i]
        # Model outputs normalized coordinates (0-1), scale to original frame size
        x1, y1 = int(b[0] * w), int(b[1] * h)
        x2, y2 = int(b[2] * w), int(b[3] * h)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w-1, x2), min(h-1, y2)
        if x2 <= x1 or y2 <= y1:
            return None
        return (x1, y1, x2, y2, best_c)

    def _get_square_crop(self, frame: NDArray, box: tuple[int, int, int, int]) -> NDArray:
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = box
        bw, bh = x2 - x1, y2 - y1
        if bh < bw:
            y1, y2 = y1 - (bw - bh) // 2, y1 - (bw - bh) // 2 + bw
        elif bh > bw:
            x1, x2 = x1 - (bh - bw) // 2, x1 - (bh - bw) // 2 + bh
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w-1, x2), min(h-1, y2)
        return frame[y1:y2, x1:x2]

    def _classify(self, crop: NDArray) -> tuple[Gesture, float]:
        if self._classifier is None or crop.size == 0:
            return Gesture.NONE, 0.0
        inp = self._preprocess(crop, self._classifier_size)
        logits = self._classifier.run(None, {self._cls_input: inp})[0][0]
        idx = int(np.argmax(logits))
        exp_l = np.exp(logits - np.max(logits))
        conf = float(exp_l[idx] / np.sum(exp_l))
        if idx >= len(_GESTURE_CLASSES) or conf < self._confidence_threshold:
            return Gesture.NONE, conf
        name = _GESTURE_CLASSES[idx]
        return _NAME_TO_GESTURE.get(name, Gesture.NONE), conf

    def detect(self, frame: NDArray) -> tuple[Gesture, float]:
        if not self._available:
            return Gesture.NONE, 0.0
        try:
            det = self._detect_hand(frame)
            if det is None:
                return Gesture.NONE, 0.0
            x1, y1, x2, y2, det_c = det
            logger.debug("Hand: box=(%d,%d,%d,%d) conf=%.2f", x1, y1, x2, y2, det_c)
            crop = self._get_square_crop(frame, (x1, y1, x2, y2))
            if crop.size == 0:
                return Gesture.NONE, 0.0
            gest, cls_c = self._classify(crop)
            if gest != Gesture.NONE:
                logger.debug("Gesture: %s (det=%.2f cls=%.2f)", gest.value, det_c, cls_c)
            return gest, det_c * cls_c
        except Exception as e:
            logger.warning("Gesture error: %s", e)
            return Gesture.NONE, 0.0

    def close(self) -> None:
        self._detector = self._classifier = None
        self._available = False
