"""Lightweight head tracker using YOLO for face detection.

Ported from reachy_mini_conversation_app for voice assistant integration.
Model is loaded at initialization time (not lazy) to ensure face tracking
is ready immediately when the camera server starts.

Performance Optimizations:
- Optional frame downscaling for faster inference on low-power devices
- Frame skip support for reduced CPU usage when tracking is stable
- Configurable inference resolution (default: native resolution)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)


class HeadTracker:
    """Lightweight head tracker using YOLO for face detection.

    Model is loaded at initialization time to ensure face tracking
    is ready immediately (matching conversation_app behavior).

    Performance Features:
    - Frame downscaling: Reduces inference resolution for ~4x speedup
    - Frame skipping: Reuses last detection result for stable tracking
    """

    def __init__(
        self,
        model_repo: str = "AdamCodd/YOLOv11n-face-detection",
        model_filename: str = "model.pt",
        confidence_threshold: float = 0.3,
        device: str = "cpu",
        inference_scale: float = 1.0,  # Scale factor for inference (0.5 = half resolution)
    ) -> None:
        """Initialize YOLO-based head tracker.

        Args:
            model_repo: HuggingFace model repository
            model_filename: Model file name
            confidence_threshold: Minimum confidence for face detection
            device: Device to run inference on ('cpu' or 'cuda')
            inference_scale: Scale factor for inference (0.5 = half res for ~4x speedup)
        """
        self.confidence_threshold = confidence_threshold
        self.model = None
        self._model_repo = model_repo
        self._model_filename = model_filename
        self._device = device
        self._detections_class = None
        self._model_load_attempted = False
        self._model_load_error: str | None = None

        # Performance optimization settings
        self._inference_scale = min(1.0, max(0.25, inference_scale))

        # Frame skip support for stable tracking
        self._last_detection: tuple[NDArray, float] | None = None
        self._frames_since_detection = 0
        self._max_skip_frames = 0  # 0 = no skipping (can be set externally)

        # Load model immediately at init (not lazy)
        self._load_model()

    def _load_model(self) -> None:
        """Load YOLO model for face detection."""
        if self._model_load_attempted:
            return

        self._model_load_attempted = True

        try:
            from pathlib import Path

            from supervision import Detections
            from ultralytics import YOLO

            self._detections_class = Detections

            # Load local model from models directory
            models_dir = Path(__file__).resolve().parents[1] / "models"
            local_model_path = models_dir / self._model_filename

            if not local_model_path.exists():
                raise FileNotFoundError(
                    f"Model file not found: {local_model_path}. "
                    f"Please place {self._model_filename} in the models directory."
                )

            model_path = str(local_model_path)
            logger.info("Loading local YOLO model: %s", model_path)

            self.model = YOLO(model_path).to(self._device)
            logger.info("YOLO face detection model loaded successfully")
        except ImportError as e:
            self._model_load_error = f"Missing dependencies: {e}"
            logger.warning("Face tracking disabled - missing dependencies: %s", e)
            self.model = None
        except FileNotFoundError as e:
            self._model_load_error = str(e)
            logger.error("Failed to load YOLO model: %s", e)
            self.model = None
        except Exception as e:
            self._model_load_error = str(e)
            logger.error("Failed to load YOLO model: %s", e)
            self.model = None

    @property
    def is_available(self) -> bool:
        """Check if the head tracker is available and ready."""
        return self.model is not None and self._detections_class is not None

    def _select_best_face(self, detections) -> int | None:
        """Select the best face based on confidence and area.

        Args:
            detections: Supervision detections object

        Returns:
            Index of best face or None if no valid faces
        """
        if detections.xyxy.shape[0] == 0:
            return None

        if detections.confidence is None:
            return None

        # Filter by confidence threshold
        valid_mask = detections.confidence >= self.confidence_threshold
        if not np.any(valid_mask):
            return None

        valid_indices = np.where(valid_mask)[0]

        # Calculate areas for valid detections
        boxes = detections.xyxy[valid_indices]
        areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])

        # Combine confidence and area (weighted towards larger faces)
        confidences = detections.confidence[valid_indices]
        scores = confidences * 0.7 + (areas / np.max(areas)) * 0.3

        best_idx = valid_indices[np.argmax(scores)]
        return int(best_idx)

    def _bbox_to_normalized_coords(self, bbox: NDArray[np.float32], w: int, h: int) -> NDArray[np.float32]:
        """Convert bounding box center to normalized coordinates [-1, 1].

        Args:
            bbox: Bounding box [x1, y1, x2, y2]
            w: Image width
            h: Image height

        Returns:
            Center point in [-1, 1] coordinates
        """
        center_x = (bbox[0] + bbox[2]) / 2.0
        center_y = (bbox[1] + bbox[3]) / 2.0

        # Normalize to [0, 1] then to [-1, 1]
        norm_x = (center_x / w) * 2.0 - 1.0
        norm_y = (center_y / h) * 2.0 - 1.0

        return np.array([norm_x, norm_y], dtype=np.float32)

    def get_head_position(self, img: NDArray[np.uint8]) -> tuple[NDArray[np.float32] | None, float | None]:
        """Get head position from face detection.

        Args:
            img: Input image (BGR format)

        Returns:
            Tuple of (face_center [-1,1], confidence) or (None, None) if no face
        """
        if not self.is_available:
            return None, None

        h, w = img.shape[:2]

        # Frame skip optimization: return last detection if within skip limit
        if (
            self._max_skip_frames > 0
            and self._last_detection is not None
            and self._frames_since_detection < self._max_skip_frames
        ):
            self._frames_since_detection += 1
            return self._last_detection

        try:
            # Downscale image for faster inference if scale < 1.0
            if self._inference_scale < 1.0:
                import cv2

                new_w = int(w * self._inference_scale)
                new_h = int(h * self._inference_scale)
                inference_img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
            else:
                inference_img = img
                new_w, new_h = w, h

            # Run YOLO inference
            results = self.model(inference_img, verbose=False)
            detections = self._detections_class.from_ultralytics(results[0])

            # Select best face
            face_idx = self._select_best_face(detections)
            if face_idx is None:
                self._last_detection = None
                self._frames_since_detection = 0
                return None, None

            bbox = detections.xyxy[face_idx]
            confidence = None
            if detections.confidence is not None:
                confidence = float(detections.confidence[face_idx])

            # Scale bbox back to original resolution if downscaled
            if self._inference_scale < 1.0:
                scale_factor = 1.0 / self._inference_scale
                bbox = bbox * scale_factor

            # Get face center in [-1, 1] coordinates (using original dimensions)
            face_center = self._bbox_to_normalized_coords(bbox, w, h)

            # Cache result for frame skipping
            self._last_detection = (face_center, confidence)
            self._frames_since_detection = 0

            return face_center, confidence

        except Exception as e:
            logger.debug("Error in head position detection: %s", e)
            return None, None

    def set_inference_scale(self, scale: float) -> None:
        """Set the inference resolution scale factor.

        Args:
            scale: Scale factor (0.25 to 1.0). Lower = faster but less accurate.
        """
        self._inference_scale = min(1.0, max(0.25, scale))
        logger.debug("Inference scale set to %.2f", self._inference_scale)

    def set_max_skip_frames(self, skip: int) -> None:
        """Set maximum frames to skip between detections.

        Args:
            skip: Number of frames to skip (0 = no skipping).
                  Higher values reduce CPU but may cause tracking lag.
        """
        self._max_skip_frames = max(0, skip)
        logger.debug("Max skip frames set to %d", self._max_skip_frames)

    def clear_detection_cache(self) -> None:
        """Clear cached detection result."""
        self._last_detection = None
        self._frames_since_detection = 0

    def suspend(self) -> None:
        """Suspend the head tracker to release YOLO model from memory.

        Call resume() to reload the model.
        """
        if self.model is None:
            logger.debug("HeadTracker model not loaded, nothing to suspend")
            return

        logger.info("Suspending HeadTracker - releasing YOLO model...")

        try:
            # Release YOLO model from memory
            del self.model
            self.model = None

            # Also clear the detections class reference
            self._detections_class = None

            # Reset load state so resume can reload
            self._model_load_attempted = False
            self._model_load_error = None

            # Clear detection cache
            self.clear_detection_cache()

            logger.info("HeadTracker suspended - YOLO model released")
        except Exception as e:
            logger.warning("Error suspending HeadTracker: %s", e)

    def resume(self) -> None:
        """Resume the head tracker by reloading the YOLO model."""
        if self.model is not None:
            logger.debug("HeadTracker model already loaded")
            return

        logger.info("Resuming HeadTracker - reloading YOLO model...")

        # Reload the model
        self._load_model()

        if self.is_available:
            logger.info("HeadTracker resumed - YOLO model loaded")
        else:
            logger.warning("HeadTracker resume failed - model not available")
