"""Gesture detection using HaGRID ONNX models.

Uses models from ai-forever/dynamic_gestures:
- hand_detector.onnx (~1.2MB): Detects hand bounding boxes
- crops_classifier.onnx (~0.4MB): Classifies hand gestures (18 HaGRID classes)

Total size: ~1.6MB - optimized for Raspberry Pi CM4.
"""

from __future__ import annotations
import logging
import time
from enum import Enum
from pathlib import Path
from typing import Optional, Callable, Dict, Tuple, List

import cv2
import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)


class Gesture(Enum):
    """HaGRID gesture classes."""
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


# HaGRID class names in order (from crops_classifier output)
_HAGRID_CLASSES = [
    "call", "dislike", "fist", "four", "like", "mute", "ok", "one",
    "palm", "peace", "peace_inverted", "rock", "stop", "stop_inverted",
    "three", "three2", "two_up", "two_up_inverted"
]

_NAME_TO_GESTURE = {name: Gesture(name) for name in _HAGRID_CLASSES}


class GestureDetector:
    """Gesture detector using HaGRID ONNX models.
    
    Two-stage pipeline:
    1. hand_detector.onnx - finds hand bounding box
    2. crops_classifier.onnx - classifies gesture from cropped hand
    
    Optimized for Raspberry Pi CM4 (~1.6MB total).
    """

    def __init__(
        self,
        confidence_threshold: float = 0.6,
        detection_threshold: float = 0.5,
    ) -> None:
        """Initialize gesture detector.

        Args:
            confidence_threshold: Min confidence for gesture classification
            detection_threshold: Min confidence for hand detection
        """
        self._confidence_threshold = confidence_threshold
        self._detection_threshold = detection_threshold
        
        # Model paths
        models_dir = Path(__file__).parent / "models"
        self._detector_path = models_dir / "hand_detector.onnx"
        self._classifier_path = models_dir / "crops_classifier.onnx"
        
        self._detector = None
        self._classifier = None
        self._available = False
        self._model_load_error: Optional[str] = None
        
        # Callbacks
        self._callbacks: Dict[Gesture, Optional[Callable[[], None]]] = {
            g: None for g in Gesture if g != Gesture.NONE
        }
        
        # State tracking
        self._last_gesture = Gesture.NONE
        self._current_gesture = Gesture.NONE
        self._gesture_start_time: Optional[float] = None
        self._gesture_hold_threshold = 0.5  # seconds to hold
        self._gesture_cooldown = 1.5  # seconds between triggers
        self._last_trigger_time: float = 0
        self._gesture_clear_delay = 2.0
        self._last_gesture_time: float = 0
        
        # Load models
        self._load_models()

    def _load_models(self) -> None:
        """Load ONNX models."""
        try:
            import onnxruntime as ort
        except ImportError:
            self._model_load_error = "onnxruntime not installed"
            logger.warning("Gesture detection disabled - pip install onnxruntime")
            return
        
        if not self._detector_path.exists():
            self._model_load_error = f"Model not found: {self._detector_path}"
            logger.warning("Gesture detection disabled - %s", self._model_load_error)
            return
        if not self._classifier_path.exists():
            self._model_load_error = f"Model not found: {self._classifier_path}"
            logger.warning("Gesture detection disabled - %s", self._model_load_error)
            return
        
        try:
            providers = ['CPUExecutionProvider']
            logger.info("Loading gesture models...")
            self._detector = ort.InferenceSession(
                str(self._detector_path), providers=providers
            )
            self._classifier = ort.InferenceSession(
                str(self._classifier_path), providers=providers
            )
            self._available = True
            logger.info("Gesture detection ready (18 HaGRID classes)")
        except Exception as e:
            self._model_load_error = str(e)
            logger.error("Failed to load gesture models: %s", e)

    @property
    def is_available(self) -> bool:
        """Check if gesture detector is ready."""
        return self._available

    @property
    def current_gesture(self) -> Gesture:
        """Get current detected gesture."""
        return self._current_gesture

    def set_callback(self, gesture: Gesture, callback: Optional[Callable[[], None]]) -> None:
        """Set callback for a specific gesture."""
        if gesture != Gesture.NONE:
            self._callbacks[gesture] = callback

    def set_callbacks(
        self,
        on_like: Optional[Callable[[], None]] = None,
        on_dislike: Optional[Callable[[], None]] = None,
        on_stop: Optional[Callable[[], None]] = None,
        on_peace: Optional[Callable[[], None]] = None,
        on_ok: Optional[Callable[[], None]] = None,
        on_call: Optional[Callable[[], None]] = None,
        on_fist: Optional[Callable[[], None]] = None,
        on_rock: Optional[Callable[[], None]] = None,
        on_one: Optional[Callable[[], None]] = None,
        on_palm: Optional[Callable[[], None]] = None,
        on_mute: Optional[Callable[[], None]] = None,
    ) -> None:
        """Set callbacks for common gestures."""
        self._callbacks[Gesture.LIKE] = on_like
        self._callbacks[Gesture.DISLIKE] = on_dislike
        self._callbacks[Gesture.STOP] = on_stop
        self._callbacks[Gesture.PEACE] = on_peace
        self._callbacks[Gesture.OK] = on_ok
        self._callbacks[Gesture.CALL] = on_call
        self._callbacks[Gesture.FIST] = on_fist
        self._callbacks[Gesture.ROCK] = on_rock
        self._callbacks[Gesture.ONE] = on_one
        self._callbacks[Gesture.PALM] = on_palm
        self._callbacks[Gesture.MUTE] = on_mute


    def _preprocess_detector(self, frame: NDArray[np.uint8]) -> NDArray[np.float32]:
        """Preprocess frame for hand detector."""
        # Resize to model input size (assuming 320x320)
        img = cv2.resize(frame, (320, 320))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))  # HWC -> CHW
        img = np.expand_dims(img, axis=0)  # Add batch dim
        return img

    def _preprocess_classifier(self, crop: NDArray[np.uint8]) -> NDArray[np.float32]:
        """Preprocess cropped hand for classifier."""
        # Resize to classifier input size (assuming 224x224)
        img = cv2.resize(crop, (224, 224))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32) / 255.0
        # Normalize with ImageNet mean/std
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        img = (img - mean) / std
        img = np.transpose(img, (2, 0, 1))  # HWC -> CHW
        img = np.expand_dims(img, axis=0)  # Add batch dim
        return img

    def _detect_hand(self, frame: NDArray[np.uint8]) -> Optional[Tuple[int, int, int, int]]:
        """Detect hand bounding box in frame.
        
        Returns:
            (x1, y1, x2, y2) or None if no hand detected
        """
        if self._detector is None:
            return None
        
        h, w = frame.shape[:2]
        input_tensor = self._preprocess_detector(frame)
        
        # Run detector
        input_name = self._detector.get_inputs()[0].name
        outputs = self._detector.run(None, {input_name: input_tensor})
        
        # Debug: log output shape (only once)
        if not hasattr(self, '_logged_detector_shape'):
            logger.info("Hand detector output: %d tensors, shapes=%s", 
                       len(outputs), [o.shape for o in outputs])
            self._logged_detector_shape = True
        
        # Parse output (format depends on model, adjust as needed)
        # Assuming output is [batch, num_detections, 5] where 5 = [x1, y1, x2, y2, conf]
        detections = outputs[0]
        
        if len(detections.shape) == 3:
            detections = detections[0]  # Remove batch dim
        
        # Find best detection above threshold
        best_box = None
        best_conf = self._detection_threshold
        
        for det in detections:
            if len(det) >= 5:
                conf = det[4]
                if conf > best_conf:
                    best_conf = conf
                    # Scale coordinates to original frame size
                    x1 = int(det[0] * w / 320)
                    y1 = int(det[1] * h / 320)
                    x2 = int(det[2] * w / 320)
                    y2 = int(det[3] * h / 320)
                    # Clamp to frame bounds
                    x1 = max(0, min(w, x1))
                    y1 = max(0, min(h, y1))
                    x2 = max(0, min(w, x2))
                    y2 = max(0, min(h, y2))
                    if x2 > x1 and y2 > y1:
                        best_box = (x1, y1, x2, y2)
        
        return best_box

    def _classify_gesture(self, crop: NDArray[np.uint8]) -> Tuple[Gesture, float]:
        """Classify gesture from cropped hand image.
        
        Returns:
            (gesture, confidence)
        """
        if self._classifier is None:
            return Gesture.NONE, 0.0
        
        input_tensor = self._preprocess_classifier(crop)
        
        # Run classifier
        input_name = self._classifier.get_inputs()[0].name
        outputs = self._classifier.run(None, {input_name: input_tensor})
        
        # Get probabilities (softmax)
        logits = outputs[0][0]
        probs = np.exp(logits) / np.sum(np.exp(logits))
        
        # Get top prediction
        idx = np.argmax(probs)
        conf = probs[idx]
        
        if idx < len(_HAGRID_CLASSES) and conf >= self._confidence_threshold:
            gesture_name = _HAGRID_CLASSES[idx]
            return _NAME_TO_GESTURE.get(gesture_name, Gesture.NONE), float(conf)
        
        return Gesture.NONE, float(conf)


    def detect(self, frame: NDArray[np.uint8]) -> Tuple[Gesture, float]:
        """Detect gesture in frame.

        Args:
            frame: Input image (BGR format from OpenCV)

        Returns:
            Tuple of (gesture, confidence)
        """
        if not self.is_available:
            return Gesture.NONE, 0.0

        try:
            # Step 1: Detect hand
            box = self._detect_hand(frame)
            if box is None:
                return Gesture.NONE, 0.0
            
            # Step 2: Crop hand region
            x1, y1, x2, y2 = box
            crop = frame[y1:y2, x1:x2]
            
            if crop.size == 0:
                return Gesture.NONE, 0.0
            
            # Step 3: Classify gesture
            return self._classify_gesture(crop)
            
        except Exception as e:
            logger.debug("Gesture detection error: %s", e)
            return Gesture.NONE, 0.0

    def process_frame(self, frame: NDArray[np.uint8]) -> Optional[Gesture]:
        """Process frame and trigger callbacks if gesture held.

        Args:
            frame: Input image (BGR format)

        Returns:
            Triggered gesture or None
        """
        gesture, confidence = self.detect(frame)
        now = time.time()
        
        # Update current gesture for display
        if gesture != Gesture.NONE:
            self._current_gesture = gesture
            self._last_gesture_time = now
        elif now - self._last_gesture_time > self._gesture_clear_delay:
            self._current_gesture = Gesture.NONE
        
        # Check cooldown
        if now - self._last_trigger_time < self._gesture_cooldown:
            return None
        
        # Track gesture hold time
        if gesture != self._last_gesture:
            self._last_gesture = gesture
            self._gesture_start_time = now if gesture != Gesture.NONE else None
            return None
        
        # Check if gesture held long enough
        if gesture != Gesture.NONE and self._gesture_start_time:
            if now - self._gesture_start_time >= self._gesture_hold_threshold:
                self._last_trigger_time = now
                self._gesture_start_time = None
                
                # Trigger callback
                callback = self._callbacks.get(gesture)
                if callback:
                    logger.info("Gesture triggered: %s (%.1f%%)", 
                               gesture.value, confidence * 100)
                    try:
                        callback()
                    except Exception as e:
                        logger.error("Gesture callback error: %s", e)
                    return gesture
        
        return None

    def close(self) -> None:
        """Release resources."""
        self._detector = None
        self._classifier = None
        self._available = False
