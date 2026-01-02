#!/usr/bin/env python3
"""Main entry point for Reachy Mini Home Assistant Voice Assistant."""

import argparse
import asyncio
import json
import logging
import sys
import threading
import time
from pathlib import Path
from queue import Queue
from typing import Dict, List, Optional, Set, Union

import numpy as np
import sounddevice as sd

from pymicro_wakeword import MicroWakeWord, MicroWakeWordFeatures
from pyopen_wakeword import OpenWakeWord, OpenWakeWordFeatures

from .models import AvailableWakeWord, Preferences, ServerState, WakeWordType
from .audio_player import AudioPlayer
from .satellite import VoiceSatelliteProtocol
from .util import get_mac
from .zeroconf import HomeAssistantZeroconf

_LOGGER = logging.getLogger(__name__)

_MODULE_DIR = Path(__file__).parent
_REPO_DIR = _MODULE_DIR.parent
_WAKEWORDS_DIR = _REPO_DIR / "wakewords"
_SOUNDS_DIR = _REPO_DIR / "sounds"


def download_required_files():
    """Download required model and sound files if missing."""
    import urllib.request

    _WAKEWORDS_DIR.mkdir(parents=True, exist_ok=True)
    _SOUNDS_DIR.mkdir(parents=True, exist_ok=True)

    # Wake word models
    wakeword_files = {
        "okay_nabu.tflite": "https://github.com/esphome/micro-wake-word-models/raw/main/models/v2/okay_nabu.tflite",
        "okay_nabu.json": "https://github.com/esphome/micro-wake-word-models/raw/main/models/v2/okay_nabu.json",
        "hey_jarvis.tflite": "https://github.com/esphome/micro-wake-word-models/raw/main/models/v2/hey_jarvis.tflite",
        "hey_jarvis.json": "https://github.com/esphome/micro-wake-word-models/raw/main/models/v2/hey_jarvis.json",
        "stop.tflite": "https://github.com/esphome/micro-wake-word-models/raw/main/models/v2/stop.tflite",
        "stop.json": "https://github.com/esphome/micro-wake-word-models/raw/main/models/v2/stop.json",
    }

    # Sound files
    sound_files = {
        "wake_word_triggered.flac": "https://github.com/OHF-Voice/linux-voice-assistant/raw/main/sounds/wake_word_triggered.flac",
        "timer_finished.flac": "https://github.com/OHF-Voice/linux-voice-assistant/raw/main/sounds/timer_finished.flac",
    }

    for filename, url in wakeword_files.items():
        dest = _WAKEWORDS_DIR / filename
        if not dest.exists():
            _LOGGER.info("Downloading %s...", filename)
            try:
                urllib.request.urlretrieve(url, dest)
                _LOGGER.info("Downloaded %s", filename)
            except Exception as e:
                _LOGGER.warning("Failed to download %s: %s", filename, e)

    for filename, url in sound_files.items():
        dest = _SOUNDS_DIR / filename
        if not dest.exists():
            _LOGGER.info("Downloading %s...", filename)
            try:
                urllib.request.urlretrieve(url, dest)
                _LOGGER.info("Downloaded %s", filename)
            except Exception as e:
                _LOGGER.warning("Failed to download %s: %s", filename, e)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reachy Mini Home Assistant Voice Assistant"
    )
    parser.add_argument(
        "--name",
        default="Reachy Mini",
        help="Name of the voice assistant (default: Reachy Mini)",
    )
    parser.add_argument(
        "--audio-input-device",
        help="Audio input device name or index (see --list-input-devices)",
    )
    parser.add_argument(
        "--list-input-devices",
        action="store_true",
        help="List audio input devices and exit",
    )
    parser.add_argument(
        "--audio-input-block-size",
        type=int,
        default=1024,
        help="Audio input block size (default: 1024)",
    )
    parser.add_argument(
        "--audio-output-device",
        help="Audio output device name or index (see --list-output-devices)",
    )
    parser.add_argument(
        "--list-output-devices",
        action="store_true",
        help="List audio output devices and exit",
    )
    parser.add_argument(
        "--wake-word-dir",
        default=[str(_WAKEWORDS_DIR)],
        action="append",
        help="Directory with wake word models (.tflite) and configs (.json)",
    )
    parser.add_argument(
        "--wake-model",
        default="okay_nabu",
        help="Id of active wake model (default: okay_nabu)",
    )
    parser.add_argument(
        "--stop-model",
        default="stop",
        help="Id of stop model (default: stop)",
    )
    parser.add_argument(
        "--download-dir",
        default=str(_REPO_DIR / "local"),
        help="Directory to download custom wake word models, etc.",
    )
    parser.add_argument(
        "--refractory-seconds",
        default=2.0,
        type=float,
        help="Seconds before wake word can be activated again (default: 2.0)",
    )
    parser.add_argument(
        "--wakeup-sound",
        default=str(_SOUNDS_DIR / "wake_word_triggered.flac"),
        help="Sound to play when wake word is detected",
    )
    parser.add_argument(
        "--timer-finished-sound",
        default=str(_SOUNDS_DIR / "timer_finished.flac"),
        help="Sound to play when timer finishes",
    )
    parser.add_argument(
        "--preferences-file",
        default=str(_REPO_DIR / "preferences.json"),
        help="Path to preferences file",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Address for ESPHome server (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=6053,
        help="Port for ESPHome server (default: 6053)",
    )
    parser.add_argument(
        "--no-motion",
        action="store_true",
        help="Disable Reachy Mini motion control",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print DEBUG messages to console",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # List input devices
    if args.list_input_devices:
        print("\nAudio Input Devices")
        print("=" * 40)
        devices = sd.query_devices()
        for idx, device in enumerate(devices):
            if device["max_input_channels"] > 0:
                print(f"[{idx}] {device['name']}")
        return

    # List output devices
    if args.list_output_devices:
        print("\nAudio Output Devices")
        print("=" * 40)
        devices = sd.query_devices()
        for idx, device in enumerate(devices):
            if device["max_output_channels"] > 0:
                print(f"[{idx}] {device['name']}")
        return

    _LOGGER.debug(args)

    # Download required files
    download_required_files()

    # Setup paths
    download_dir = Path(args.download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)

    # Resolve audio input device
    input_device = args.audio_input_device
    if input_device is not None:
        try:
            input_device = int(input_device)
        except ValueError:
            pass

    # Load available wake words
    wake_word_dirs = [Path(ww_dir) for ww_dir in args.wake_word_dir]
    wake_word_dirs.append(download_dir / "external_wake_words")

    available_wake_words: Dict[str, AvailableWakeWord] = {}
    for wake_word_dir in wake_word_dirs:
        if not wake_word_dir.exists():
            continue
        for model_config_path in wake_word_dir.glob("*.json"):
            model_id = model_config_path.stem
            if model_id == args.stop_model:
                # Don't show stop model as an available wake word
                continue

            try:
                with open(model_config_path, "r", encoding="utf-8") as model_config_file:
                    model_config = json.load(model_config_file)

                model_type = WakeWordType(model_config.get("type", "micro"))

                if model_type == WakeWordType.OPEN_WAKE_WORD:
                    wake_word_path = model_config_path.parent / model_config["model"]
                else:
                    wake_word_path = model_config_path

                available_wake_words[model_id] = AvailableWakeWord(
                    id=model_id,
                    type=WakeWordType(model_type),
                    wake_word=model_config.get("wake_word", model_id),
                    trained_languages=model_config.get("trained_languages", []),
                    wake_word_path=wake_word_path,
                )
            except Exception as e:
                _LOGGER.warning("Failed to load wake word config %s: %s", model_config_path, e)

    _LOGGER.debug("Available wake words: %s", list(sorted(available_wake_words.keys())))

    # Load preferences
    preferences_path = Path(args.preferences_file)
    if preferences_path.exists():
        _LOGGER.debug("Loading preferences: %s", preferences_path)
        with open(preferences_path, "r", encoding="utf-8") as preferences_file:
            preferences_dict = json.load(preferences_file)
        preferences = Preferences(**preferences_dict)
    else:
        preferences = Preferences()

    # Load wake/stop models
    active_wake_words: Set[str] = set()
    wake_models: Dict[str, Union[MicroWakeWord, OpenWakeWord]] = {}

    if preferences.active_wake_words:
        # Load preferred models
        for wake_word_id in preferences.active_wake_words:
            wake_word = available_wake_words.get(wake_word_id)
            if wake_word is None:
                _LOGGER.warning("Unrecognized wake word id: %s", wake_word_id)
                continue

            _LOGGER.debug("Loading wake model: %s", wake_word_id)
            wake_models[wake_word_id] = wake_word.load()
            active_wake_words.add(wake_word_id)

    if not wake_models:
        # Load default model
        wake_word_id = args.wake_model
        wake_word = available_wake_words.get(wake_word_id)
        if wake_word:
            _LOGGER.debug("Loading wake model: %s", wake_word_id)
            wake_models[wake_word_id] = wake_word.load()
            active_wake_words.add(wake_word_id)
        else:
            _LOGGER.error("Wake word model not found: %s", wake_word_id)
            _LOGGER.error("Available models: %s", list(available_wake_words.keys()))
            sys.exit(1)

    # Load stop model
    stop_model: Optional[MicroWakeWord] = None
    for wake_word_dir in wake_word_dirs:
        stop_config_path = wake_word_dir / f"{args.stop_model}.json"
        if not stop_config_path.exists():
            continue

        _LOGGER.debug("Loading stop model: %s", stop_config_path)
        stop_model = MicroWakeWord.from_config(stop_config_path)
        break

    if stop_model is None:
        _LOGGER.warning("Stop model not found, timer stop functionality disabled")
        # Create a dummy stop model that never triggers
        stop_model = MicroWakeWord.from_config(
            list(available_wake_words.values())[0].wake_word_path
        )

    # Initialize Reachy Mini (if available)
    reachy_mini = None
    if not args.no_motion:
        try:
            from reachy_mini import ReachyMini
            reachy_mini = ReachyMini()
            _LOGGER.info("Reachy Mini connected")
        except ImportError:
            _LOGGER.warning("reachy-mini not installed, motion control disabled")
        except Exception as e:
            _LOGGER.warning("Failed to connect to Reachy Mini: %s", e)

    # Create server state
    state = ServerState(
        name=args.name,
        mac_address=get_mac(),
        audio_queue=Queue(),
        entities=[],
        available_wake_words=available_wake_words,
        wake_words=wake_models,
        active_wake_words=active_wake_words,
        stop_word=stop_model,
        music_player=AudioPlayer(device=args.audio_output_device),
        tts_player=AudioPlayer(device=args.audio_output_device),
        wakeup_sound=args.wakeup_sound,
        timer_finished_sound=args.timer_finished_sound,
        preferences=preferences,
        preferences_path=preferences_path,
        refractory_seconds=args.refractory_seconds,
        download_dir=download_dir,
        reachy_mini=reachy_mini,
        motion_enabled=not args.no_motion and reachy_mini is not None,
    )

    # Start audio processing thread
    process_audio_thread = threading.Thread(
        target=process_audio,
        args=(state, input_device, args.audio_input_block_size),
        daemon=True,
    )
    process_audio_thread.start()

    # Create ESPHome server
    loop = asyncio.get_running_loop()
    server = await loop.create_server(
        lambda: VoiceSatelliteProtocol(state), host=args.host, port=args.port
    )

    # Auto discovery (zeroconf, mDNS)
    discovery = HomeAssistantZeroconf(port=args.port, name=args.name)
    await discovery.register_server()

    try:
        async with server:
            _LOGGER.info("=" * 50)
            _LOGGER.info("Reachy Mini Voice Assistant Started")
            _LOGGER.info("=" * 50)
            _LOGGER.info("Name: %s", args.name)
            _LOGGER.info("ESPHome Server: %s:%s", args.host, args.port)
            _LOGGER.info("Wake word: %s", list(active_wake_words))
            _LOGGER.info("Motion control: %s", "enabled" if state.motion_enabled else "disabled")
            _LOGGER.info("=" * 50)
            _LOGGER.info("Add this device in Home Assistant:")
            _LOGGER.info("  Settings -> Devices & Services -> Add Integration -> ESPHome")
            _LOGGER.info("  Enter: <this-device-ip>:6053")
            _LOGGER.info("=" * 50)

            await server.serve_forever()
    except KeyboardInterrupt:
        _LOGGER.info("Shutting down...")
    finally:
        state.audio_queue.put_nowait(None)
        process_audio_thread.join(timeout=2.0)
        await discovery.unregister_server()
        _LOGGER.debug("Server stopped")


def process_audio(state: ServerState, input_device, block_size: int):
    """Process audio chunks from the microphone."""
    wake_words: List[Union[MicroWakeWord, OpenWakeWord]] = []
    micro_features: Optional[MicroWakeWordFeatures] = None
    micro_inputs: List[np.ndarray] = []
    oww_features: Optional[OpenWakeWordFeatures] = None
    oww_inputs: List[np.ndarray] = []
    has_oww = False
    last_active: Optional[float] = None

    try:
        _LOGGER.debug("Opening audio input device: %s", input_device or "default")

        with sd.InputStream(
            device=input_device,
            samplerate=16000,
            channels=1,
            blocksize=block_size,
            dtype="float32",
        ) as stream:
            while True:
                audio_chunk_array, overflowed = stream.read(block_size)
                if overflowed:
                    _LOGGER.warning("Audio buffer overflow")

                audio_chunk_array = audio_chunk_array.reshape(-1)

                # Convert to 16-bit PCM for streaming
                audio_chunk = (
                    (np.clip(audio_chunk_array, -1.0, 1.0) * 32767.0)
                    .astype("<i2")
                    .tobytes()
                )

                # Stream audio to Home Assistant
                if state.satellite:
                    state.satellite.handle_audio(audio_chunk)

                # Check if wake words changed
                if state.wake_words_changed:
                    state.wake_words_changed = False
                    wake_words = list(state.wake_words.values())
                    has_oww = any(isinstance(ww, OpenWakeWord) for ww in wake_words)

                    if any(isinstance(ww, MicroWakeWord) for ww in wake_words):
                        micro_features = MicroWakeWordFeatures()
                    else:
                        micro_features = None

                    if has_oww:
                        oww_features = OpenWakeWordFeatures.from_builtin()
                    else:
                        oww_features = None

                # Initialize features if needed
                if not wake_words:
                    wake_words = list(state.wake_words.values())
                    has_oww = any(isinstance(ww, OpenWakeWord) for ww in wake_words)

                    if any(isinstance(ww, MicroWakeWord) for ww in wake_words):
                        micro_features = MicroWakeWordFeatures()

                    if has_oww:
                        oww_features = OpenWakeWordFeatures.from_builtin()

                # Extract features
                micro_inputs.clear()
                oww_inputs.clear()

                if micro_features:
                    micro_inputs = micro_features.process_streaming(audio_chunk_array)

                if oww_features:
                    oww_inputs = oww_features.process_streaming(audio_chunk_array)

                # Process wake words
                for wake_word in wake_words:
                    if wake_word.id not in state.active_wake_words:
                        continue

                    activated = False

                    if isinstance(wake_word, MicroWakeWord):
                        for micro_input in micro_inputs:
                            if wake_word.process_streaming(micro_input):
                                activated = True
                    elif isinstance(wake_word, OpenWakeWord):
                        for oww_input in oww_inputs:
                            scores = wake_word.process_streaming(oww_input)
                            if any(s > 0.5 for s in scores):
                                activated = True

                    if activated:
                        # Check refractory period
                        now = time.monotonic()
                        if (last_active is None) or (
                            (now - last_active) > state.refractory_seconds
                        ):
                            if state.satellite:
                                state.satellite.wakeup(wake_word)
                            last_active = now

                # Always process stop word to keep state correct
                stopped = False
                for micro_input in micro_inputs:
                    if state.stop_word.process_streaming(micro_input):
                        stopped = True

                if stopped and (state.stop_word.id in state.active_wake_words):
                    if state.satellite:
                        state.satellite.stop()

    except Exception:
        _LOGGER.exception("Unexpected error processing audio")
        sys.exit(1)


def run():
    """Entry point for the application."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
