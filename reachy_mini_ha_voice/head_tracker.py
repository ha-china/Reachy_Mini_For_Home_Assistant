"""Lightweight head tracker using YOLO for face detection.

Ported from reachy_mini_conversation_app for voice assistant integration.
"""

from __future__ import annotations
import logging
from typing import Tuple, Optional

import numpy as np
from numpy.typing import NDArray


logger = logging.getLogger(__name__)

# Lazy imports to avoid startup delay
_YOLO = None
_Detections = None


def _load_yolo_deps():
    """Lazy load YOLO dependencies."""
    global _YOLO, _Detections
    if _YOLO is None:
        try:
            from ultralytics import YOLO
            from supervision import Detections
            _YOLO = YOLO
            _Detections = Detections
        except ImportError as e:
            raise ImportError(
                "To use head tracker, install: pip install ultralytics supervision huggingface_hub"
            ) from e
    return _YOLO, _Detections


class HeadTracker:
    """Lightweight head tracker using YOLO for face detection."""

    def __init__(
        self,
        model_repo: str = "AdamCodd/YOLOv11n-face-detection",
        model_filename: str = "model.pt",
        confidence_threshold: float = 0.3,
        device: str = "cpu",
    ) -> None:
        """Initialize YOLO-based head tracker.

        Args:
            model_repo: HuggingFace model repository
            model_filename: Model file name
            confidence_threshold: Minimum confidence for face detection
            device: Device to run inference on ('cpu' or 'cuda')
        """
        self.confidence_threshold = confidence_threshold
        self.model = None
        self._model_repo = model_repo
        self._model_filename = model_filename
        self._device = device
        self._initialized = False

    def _ensure_initialized(self) -> bool:
        """Lazy initialization of YOLO model."""
        if self._initialized:
            return self.model is not None
        
        self._initialized = True
        try:
            YOLO, _ = _load_yolo_deps()
            from huggingface_hub import hf_hub_download
            
            model_path = hf_hub_download(
                repo_id=self._model_repo, 
                filename=self._model_filename
            )
            self.model = YOLO(model_path).to(self._device)
            logger.info(f"YOLO face detection model loaded from {self._model_repo}")
            return True
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            self.model = None
            return False

    def _select_best_face(self, detections) -> Optional[int]:
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

    def _bbox_to_normalized_coords(
        self, bbox: NDArray[np.float32], w: int, h: int
    ) -> NDArray[np.float32]:
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

    def get_head_position(
        self, img: NDArray[np.uint8]
    ) -> Tuple[Optional[NDArray[np.float32]], Optional[float]]:
        """Get head position from face detection.

        Args:
            img: Input image (BGR format)

        Returns:
            Tuple of (face_center [-1,1], confidence) or (None, None) if no face
        """
        if not self._ensure_initialized():
            return None, None

        _, Detections = _load_yolo_deps()
        
        h, w = img.shape[:2]

        try:
            # Run YOLO inference
            results = self.model(img, verbose=False)
            detections = Detections.from_ultralytics(results[0])

            # Select best face
            face_idx = self._select_best_face(detections)
            if face_idx is None:
                return None, None

            bbox = detections.xyxy[face_idx]
            confidence = None
            if detections.confidence is not None:
                confidence = float(detections.confidence[face_idx])

            # Get face center in [-1, 1] coordinates
            face_center = self._bbox_to_normalized_coords(bbox, w, h)

            return face_center, confidence

        except Exception as e:
            logger.error(f"Error in head position detection: {e}")
            return None, None
