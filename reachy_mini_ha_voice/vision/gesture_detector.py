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
    "hand_down",
    "hand_right",
    "hand_left",
    "thumb_index",
    "thumb_left",
    "thumb_right",
    "thumb_down",
    "half_up",
    "half_left",
    "half_right",
    "half_down",
    "part_hand_heart",
    "part_hand_heart2",
    "fist_inverted",
    "two_left",
    "two_right",
    "two_down",
    "grabbing",
    "grip",
    "point",
    "call",
    "three3",
    "little_finger",
    "middle_finger",
    "dislike",
    "fist",
    "four",
    "like",
    "mute",
    "ok",
    "one",
    "palm",
    "peace",
    "peace_inverted",
    "rock",
    "stop",
    "stop_inverted",
    "three",
    "three2",
    "two_up",
    "two_up_inverted",
    "three_gun",
    "one_left",
    "one_right",
    "one_down",
]

_NAME_TO_GESTURE = {
    "call": Gesture.CALL,
    "dislike": Gesture.DISLIKE,
    "fist": Gesture.FIST,
    "four": Gesture.FOUR,
    "like": Gesture.LIKE,
    "mute": Gesture.MUTE,
    "ok": Gesture.OK,
    "one": Gesture.ONE,
    "palm": Gesture.PALM,
    "peace": Gesture.PEACE,
    "peace_inverted": Gesture.PEACE_INVERTED,
    "rock": Gesture.ROCK,
    "stop": Gesture.STOP,
    "stop_inverted": Gesture.STOP_INVERTED,
    "three": Gesture.THREE,
    "three2": Gesture.THREE2,
    "two_up": Gesture.TWO_UP,
    "two_up_inverted": Gesture.TWO_UP_INVERTED,
}


class GestureDetector:
    def __init__(self):
        models_dir = Path(__file__).parent / "models"
        fallback_models_dir = Path(__file__).resolve().parents[1] / "models"
        self._detector_path = models_dir / "hand_detector.onnx"
        self._classifier_path = models_dir / "crops_classifier.onnx"
        if not self._detector_path.exists() or not self._classifier_path.exists():
            alt_detector = fallback_models_dir / "hand_detector.onnx"
            alt_classifier = fallback_models_dir / "crops_classifier.onnx"
            if alt_detector.exists() and alt_classifier.exists():
                self._detector_path = alt_detector
                self._classifier_path = alt_classifier
        self._detector = None
        self._classifier = None
        self._available = False
        self._mean = np.array([127, 127, 127], dtype=np.float32)
        self._std = np.array([128, 128, 128], dtype=np.float32)
        self._detector_size = (320, 240)
        self._classifier_size = (128, 128)
        self._load_models()

        # Initialize gesture smoother - follows reference implementation
        # Uses history tracking without confidence filtering
        try:
            from .gesture_smoother import GestureSmoother

            self._smoother = GestureSmoother(history_size=5)
            logger.info("Gesture smoother enabled (5-frame history, no confidence filtering)")
        except ImportError:
            self._smoother = None
            logger.warning("Gesture smoother not available")

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
            providers = ["CPUExecutionProvider"]
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

    def _detect_hand(self, frame: NDArray) -> tuple[NDArray, NDArray]:
        """Detect all hands in frame.

        Returns:
            Tuple of (boxes, scores) where boxes is (N, 4) array and scores is (N,) array
        """
        if self._detector is None:
            return np.empty((0, 4)), np.empty((0,))
        h, w = frame.shape[:2]
        inp = self._preprocess(frame, self._detector_size)
        outs = self._detector.run(self._det_outputs, {self._det_input: inp})
        boxes = outs[0]
        scores = outs[2]

        # Return all detections (no threshold filtering - let downstream handle it)
        if len(boxes) == 0:
            return np.empty((0, 4)), np.empty((0,))

        # Scale normalized coordinates to original frame size
        boxes[:, 0] *= w  # x1
        boxes[:, 1] *= h  # y1
        boxes[:, 2] *= w  # x2
        boxes[:, 3] *= h  # y2

        # Clip to image boundaries
        boxes[:, 0] = np.clip(boxes[:, 0], 0, w - 1).astype(np.int32)
        boxes[:, 1] = np.clip(boxes[:, 1], 0, h - 1).astype(np.int32)
        boxes[:, 2] = np.clip(boxes[:, 2], 0, w - 1).astype(np.int32)
        boxes[:, 3] = np.clip(boxes[:, 3], 0, h - 1).astype(np.int32)

        # Filter out invalid boxes (x2 <= x1 or y2 <= y1)
        valid_boxes = (boxes[:, 2] > boxes[:, 0]) & (boxes[:, 3] > boxes[:, 1])
        boxes = boxes[valid_boxes]
        scores = scores[valid_boxes]

        return boxes, scores

    def _get_square_crop(self, frame: NDArray, boxes: NDArray) -> list[NDArray]:
        """Get square crops from frame for multiple boxes.

        Args:
            frame: Input image
            boxes: Array of bounding boxes with shape (N, 4) as [x1, y1, x2, y2]

        Returns:
            List of cropped images
        """
        h, w = frame.shape[:2]
        crops = []
        for box in boxes:
            x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
            bw, bh = x2 - x1, y2 - y1
            if bh < bw:
                y1 = y1 - (bw - bh) // 2
                y2 = y1 + bw
            elif bh > bw:
                x1 = x1 - (bh - bw) // 2
                x2 = x1 + bh
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w - 1, x2), min(h - 1, y2)
            crops.append(frame[y1:y2, x1:x2])
        return crops

    def _classify(self, crops: list[NDArray]) -> tuple[list[Gesture], list[float]]:
        """Classify multiple hand crops.

        Args:
            crops: List of cropped hand images

        Returns:
            Tuple of (gestures, confidences) lists
        """
        if self._classifier is None or len(crops) == 0:
            return [], []

        # Preprocess all crops and batch classify
        processed_crops = [self._preprocess(crop, self._classifier_size) for crop in crops if crop.size > 0]
        if len(processed_crops) == 0:
            return [], []

        # Concatenate along batch dimension
        batch_input = np.concatenate(processed_crops, axis=0)
        logits = self._classifier.run(None, {self._cls_input: batch_input})[0]

        gestures = []
        confidences = []
        for logit in logits:
            idx = int(np.argmax(logit))
            exp_l = np.exp(logit - np.max(logit))
            conf = float(exp_l[idx] / np.sum(exp_l))
            # No confidence filtering - return all classifications
            # This allows Home Assistant to see all detected gestures with their confidence levels
            if idx >= len(_GESTURE_CLASSES):
                gestures.append(Gesture.NONE)
            else:
                name = _GESTURE_CLASSES[idx]
                gestures.append(_NAME_TO_GESTURE.get(name, Gesture.NONE))
            confidences.append(conf)

        return gestures, confidences

    def detect(self, frame: NDArray) -> tuple[Gesture, float]:
        if not self._available:
            return Gesture.NONE, 0.0
        try:
            # Detect all hands
            boxes, det_scores = self._detect_hand(frame)
            if len(boxes) == 0:
                # Update smoother with no gesture
                if self._smoother:
                    confirmed_gesture_name = self._smoother.update("none", 0.0)
                    return (
                        _NAME_TO_GESTURE.get(confirmed_gesture_name, Gesture.NONE),
                        0.0,
                    )
                return Gesture.NONE, 0.0

            logger.debug("Detected %d hand(s)", len(boxes))

            # Get crops for all detected hands
            crops = self._get_square_crop(frame, boxes)
            valid_crops = [crop for crop in crops if crop.size > 0]
            if len(valid_crops) == 0:
                if self._smoother:
                    confirmed_gesture_name = self._smoother.update("none", 0.0)
                    return (
                        _NAME_TO_GESTURE.get(confirmed_gesture_name, Gesture.NONE),
                        0.0,
                    )
                return Gesture.NONE, 0.0

            # Classify all crops
            gestures, cls_scores = self._classify(valid_crops)

            # Find the gesture with highest combined confidence
            best_gesture = Gesture.NONE
            best_confidence = 0.0
            for gest, cls_c, det_c in zip(gestures, cls_scores, det_scores, strict=True):
                combined_conf = det_c * cls_c
                # Allow all gestures including low confidence ones (reference behavior)
                if combined_conf > best_confidence:
                    best_gesture = gest
                    best_confidence = combined_conf
                    logger.debug(
                        "Gesture: %s (det=%.2f cls=%.2f combined=%.2f)",
                        gest.value,
                        det_c,
                        cls_c,
                        combined_conf,
                    )

            # Use gesture smoother if available
            if self._smoother:
                gesture_name = best_gesture.value if best_gesture != Gesture.NONE else "none"
                confirmed_gesture_name = self._smoother.update(gesture_name, best_confidence)
                confirmed_gesture = _NAME_TO_GESTURE.get(confirmed_gesture_name, Gesture.NONE)
                # Return current detection confidence (not aggregated)
                # This follows reference implementation which returns real-time detection
                return confirmed_gesture, best_confidence

            return best_gesture, best_confidence
        except Exception as e:
            logger.warning("Gesture error: %s", e)
            return Gesture.NONE, 0.0

    def close(self) -> None:
        self._detector = self._classifier = None
        self._available = False
