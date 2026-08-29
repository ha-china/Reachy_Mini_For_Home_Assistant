"""Bundled model asset management.

Ensures required SDK model files (e.g. the daemon-side YuNet face tracker
model) are present in the Hugging Face cache so the SDK does not need to
download them at runtime.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

# YuNet face tracker model used by the SDK daemon-side tracker.
_FACE_DETECTOR_REPO = "pollen-robotics/face_detection_yunet_2026may"
_FACE_DETECTOR_REVISION = "2b8e922362946a0db67e861bae0f77826980effd"
_FACE_DETECTOR_FILE = "face_detection_yunet_2026may.onnx"

_MODELS_DIR = Path(__file__).resolve().parent.parent / "models"


def _hf_cache_root() -> Path | None:
    """Return the Hugging Face hub cache root, or None if unavailable."""
    try:
        from huggingface_hub.constants import HF_HUB_CACHE

        return Path(HF_HUB_CACHE)
    except Exception:
        return None


def _hf_pointer_path(cache_root: Path, repo_id: str, revision: str, filename: str) -> Path:
    """Return the cache pointer path the SDK's ``hf_hub_download`` checks first."""
    storage_folder = cache_root / f"models--{repo_id.replace('/', '--')}"
    return storage_folder / "snapshots" / revision / filename


def ensure_face_tracking_model_cached() -> bool:
    """Copy the bundled YuNet face tracker model into the HF cache if missing.

    The SDK daemon-side face tracker loads the model via ``hf_hub_download``.
    When the requested revision is a commit hash, ``hf_hub_download`` returns
    immediately without any network call if the file already exists at
    ``snapshots/<revision>/<filename>``. Seeding that path with the bundled
    model avoids a runtime download on first face-tracker activation.
    """
    cache_root = _hf_cache_root()
    if cache_root is None:
        _LOGGER.debug("huggingface_hub unavailable; cannot seed SDK face tracking model")
        return False

    pointer = _hf_pointer_path(
        cache_root,
        _FACE_DETECTOR_REPO,
        _FACE_DETECTOR_REVISION,
        _FACE_DETECTOR_FILE,
    )
    if pointer.exists():
        return True

    source = _MODELS_DIR / _FACE_DETECTOR_FILE
    if not source.exists():
        _LOGGER.warning("Bundled face tracking model missing: %s", source)
        return False

    try:
        pointer.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, pointer)
        _LOGGER.info("Seeded SDK face tracking model into HF cache: %s", pointer)
        return True
    except Exception as e:
        _LOGGER.warning("Failed to seed face tracking model into HF cache: %s", e)
        return False
