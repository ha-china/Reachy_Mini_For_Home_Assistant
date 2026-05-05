"""External wake word asset helpers for `VoiceSatelliteProtocol`."""

from __future__ import annotations

import json
import hashlib
import logging
import posixpath
import shutil
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse, urlunparse
from urllib.request import urlopen

from pymicro_wakeword import MicroWakeWord
from pyopen_wakeword import OpenWakeWord

from ..models import AvailableWakeWord, WakeWordType

if TYPE_CHECKING:
    from aioesphomeapi.api_pb2 import VoiceAssistantExternalWakeWord  # type: ignore[attr-defined]
    from .satellite import VoiceSatelliteProtocol

logger = logging.getLogger(__name__)


def get_wake_word_dirs(wakewords_dir: Path, local_dir: Path) -> list[Path]:
    return [
        wakewords_dir / "openWakeWord",
        local_dir / "external_wake_words",
        wakewords_dir,
    ]


def find_available_wake_words(wake_word_dirs: list[Path], stop_model_id: str = "stop") -> dict[str, AvailableWakeWord]:
    available_wake_words: dict[str, AvailableWakeWord] = {}

    for wake_word_dir in wake_word_dirs:
        if not wake_word_dir.exists():
            continue

        for model_config_path in wake_word_dir.glob("*.json"):
            model_id = model_config_path.stem
            if model_id == stop_model_id:
                continue

            try:
                with open(model_config_path, encoding="utf-8") as model_config_file:
                    model_config = json.load(model_config_file)

                model_type = WakeWordType(model_config["type"])
                if model_type == WakeWordType.OPEN_WAKE_WORD:
                    wake_word_path = model_config_path.parent / model_config["model"]
                else:
                    wake_word_path = model_config_path

                type_config = model_config.get(model_type.value, {})
                available_wake_words[model_id] = AvailableWakeWord(
                    id=model_id,
                    type=model_type,
                    wake_word=model_config["wake_word"],
                    trained_languages=model_config.get("trained_languages", []),
                    wake_word_path=wake_word_path,
                    probability_cutoff=type_config.get("probability_cutoff", 0.7),
                )
            except Exception as exc:
                logger.warning("Failed to load wake word %s: %s", model_config_path, exc)

    return available_wake_words


def load_wake_models(
    available_wake_words: dict[str, AvailableWakeWord],
    active_wake_word_ids: list[str] | None,
    default_wake_word_id: str,
) -> tuple[dict[str, MicroWakeWord | OpenWakeWord], set[str]]:
    wake_models: dict[str, MicroWakeWord | OpenWakeWord] = {}
    active_wake_words: set[str] = set()

    if active_wake_word_ids:
        for wake_word_id in active_wake_word_ids:
            wake_word = available_wake_words.get(wake_word_id)
            if wake_word is None:
                logger.warning("Unknown wake word ID: %s - skipping", wake_word_id)
                continue

            try:
                loaded_model = wake_word.load()
                loaded_model.id = wake_word_id
                wake_models[wake_word_id] = loaded_model
                active_wake_words.add(wake_word_id)
            except Exception as exc:
                logger.error("Failed to load wake model %s: %s", wake_word_id, exc, exc_info=True)

    if wake_models:
        return wake_models, active_wake_words

    fallback_ids = [default_wake_word_id, "okay_nabu", *available_wake_words.keys()]
    for wake_word_id in fallback_ids:
        wake_word = available_wake_words.get(wake_word_id)
        if wake_word is None:
            continue
        try:
            loaded_model = wake_word.load()
            loaded_model.id = wake_word_id
            wake_models[wake_word_id] = loaded_model
            active_wake_words.add(wake_word_id)
            return wake_models, active_wake_words
        except Exception as exc:
            logger.error("Failed to load fallback wake model %s: %s", wake_word_id, exc, exc_info=True)

    raise RuntimeError("No wake word models available in any search directory")


def load_stop_model(wake_word_dirs: list[Path], stop_model_id: str = "stop") -> MicroWakeWord | None:
    for wake_word_dir in wake_word_dirs:
        stop_config_path = wake_word_dir / f"{stop_model_id}.json"
        if not stop_config_path.exists():
            continue
        try:
            return MicroWakeWord.from_config(stop_config_path)
        except Exception as exc:
            logger.error("Failed to load stop model from %s: %s", stop_config_path, exc, exc_info=True)

    logger.error("Stop model '%s' could not be found in any search directory", stop_model_id)
    return None


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
