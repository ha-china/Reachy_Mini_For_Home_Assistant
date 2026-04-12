"""External wake word asset helpers for `VoiceSatelliteProtocol`."""

from __future__ import annotations

import hashlib
import logging
import posixpath
import shutil
from typing import TYPE_CHECKING
from urllib.parse import urlparse, urlunparse
from urllib.request import urlopen

from ..models import AvailableWakeWord, WakeWordType

if TYPE_CHECKING:
    from aioesphomeapi.api_pb2 import VoiceAssistantExternalWakeWord  # type: ignore[attr-defined]
    from .satellite import VoiceSatelliteProtocol

logger = logging.getLogger(__name__)


def download_external_wake_word(
    protocol: "VoiceSatelliteProtocol", external_wake_word: "VoiceAssistantExternalWakeWord"
) -> AvailableWakeWord | None:
    eww_dir = protocol.state.download_dir / "external_wake_words"
    eww_dir.mkdir(parents=True, exist_ok=True)

    config_path = eww_dir / f"{external_wake_word.id}.json"
    should_download_config = not config_path.exists()

    model_path = eww_dir / f"{external_wake_word.id}.tflite"
    should_download_model = True

    if model_path.exists():
        model_size = model_path.stat().st_size
        if model_size == external_wake_word.model_size:
            with open(model_path, "rb") as model_file:
                model_hash = hashlib.sha256(model_file.read()).hexdigest()
            if model_hash == external_wake_word.model_hash:
                should_download_model = False
                logger.debug("Model size and hash match for %s. Skipping download.", external_wake_word.id)

    if should_download_config or should_download_model:
        logger.debug("Downloading %s to %s", external_wake_word.url, config_path)
        with urlopen(external_wake_word.url) as request:
            if request.status != 200:
                logger.warning("Failed to download: %s, status=%s", external_wake_word.url, request.status)
                return None
            with open(config_path, "wb") as model_file:
                shutil.copyfileobj(request, model_file)

    if should_download_model:
        parsed_url = urlparse(external_wake_word.url)
        parsed_url = parsed_url._replace(path=posixpath.join(posixpath.dirname(parsed_url.path), model_path.name))
        model_url = urlunparse(parsed_url)

        logger.debug("Downloading %s to %s", model_url, model_path)
        with urlopen(model_url) as request:
            if request.status != 200:
                logger.warning("Failed to download: %s, status=%s", model_url, request.status)
                return None
            with open(model_path, "wb") as model_file:
                shutil.copyfileobj(request, model_file)

    return AvailableWakeWord(
        id=external_wake_word.id,
        type=WakeWordType.MICRO_WAKE_WORD,
        wake_word=external_wake_word.wake_word,
        trained_languages=external_wake_word.trained_languages,
        wake_word_path=config_path,
    )
