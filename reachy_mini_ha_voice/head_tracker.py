"""Lightweight head tracker using YOLO for face detection.

Model is downloaded from HuggingFace on first use and cached locally.
"""

from __future__ import annotations
import logging
import time
from pathlib import Path
from typing import Tuple, Optional

import numpy as np
from numpy.typing import NDArray


logger = logging.getLogger(__name__)

# Model config
_MODEL_REPO = "AdamCodd/YOLOv11n-face-detection"
_MODEL_FILENAME = "model.pt"
_MAX_RETRIES = 3
_RETRY_DELAY = 5  # seconds


class HeadTracker:
    """Lightweight head tracker using YOLO for face detection."""

    def __init__(
        self,
        confidence_threshold: float = 0.3,
        device: str = "cpu",
    ) -> None:
        """Initialize YOLO-based head tracker.

        Args:
            confidence_threshold: Minimum confidence for face detection
            device: Device to run inference on ('cpu' or 'cuda')
        """
        self.confidence_threshold = confidence_threshold
        self.model = None
        self._device = device
        self._detections_class = None
        self._model_load_attempted = False
        self._model_load_error: Optional[str] = None
        
        self._load_model()

    def _load_model(self) -> None:
        """Load YOLO model with retry logic."""
        if self._model_load_attempted:
            return
        
        self._model_load_attempted = True
        
        try:
            from ultralytics import YOLO
            from supervision import Detections
            from huggingface_hub import hf_hub_download
            
            self._detections_class = Detections
            
            # Download with retries
            model_path = None
            last_error = None
            
            for attempt in range(_MAX_RETRIES):
                try:
                    model_path = hf_hub_download(
                        repo_id=_MODEL_REPO,
                        filename=_MODEL_FILENAME,
                    )
                    break
                except Exception as e:
                    last_error = e
                    if attempt < _MAX_RETRIES - 1:
                        logger.warning(
                            "Model download failed (attempt %d/%d): %s. Retrying in %ds...",
                            attempt + 1, _MAX_RETRIES, e, _RETRY_DELAY
                        )
                        time.sleep(_RETRY_DELAY)
            
            if model_path is None:
                raise last_error
            
            self.model = YOLO(model_path).to(self._device)
            logger.info("YOLO face detection model loaded")
        except ImportError as e:
            self._model_load_error = f"Missing dependencies: {e}"
            logger.warning("Face tracking disabled - missing dependencies: %s", e)
            self.model = None
        except Exception as e:
            self._model_load_error = str(e)
            logger.error("Failed to load YOLO model: %s", e)
            self.model = None

    @property
    def is_available(self) -> bool:
        """Check if the head tracker is available and ready."""
        return self.model is not None and self._detections_class is not None

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
        if not self.is_available:
            return None, None

        h, w = img.shape[:2]

        try:
            # Run YOLO inference
            results = self.model(img, verbose=False)
            detections = self._detections_class.from_ultralytics(results[0])

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
            logger.debug("Error in head position detection: %s", e)
            return None, None
