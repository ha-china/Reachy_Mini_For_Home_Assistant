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
import pyaudio
from pymicro_wakeword import MicroWakeWord, MicroWakeWordFeatures
from pyopen_wakeword import OpenWakeWord, OpenWakeWordFeatures

from .models import AvailableWakeWord, Preferences, ServerState, WakeWordType, AudioPlayer
from .satellite import VoiceSatelliteProtocol
from .util import get_mac
from .zeroconf import HomeAssistantZeroconf
from .reachy_integration import ReachyMiniIntegration

_LOGGER = logging.getLogger(__name__)
_MODULE_DIR = Path(__file__).parent
_REPO_DIR = _MODULE_DIR.parent
_WAKEWORDS_DIR = _REPO_DIR / "wakewords"
_SOUNDS_DIR = _REPO_DIR / "sounds"


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Reachy Mini Voice Assistant for Home Assistant"
    )
    parser.add_argument("--name", required=True, help="Device name")
    parser.add_argument(
        "--audio-input-device",
        type=int,
        help="Audio input device index (see --list-input-devices)",
    )
    parser.add_argument(
        "--list-input-devices",
        action="store_true",
        help="List audio input devices and exit",
    )
    parser.add_argument(
        "--audio-output-device",
        type=int,
        help="Audio output device index (see --list-output-devices)",
    )
    parser.add_argument(
        "--list-output-devices",
        action="store_true",
        help="List audio output devices and exit",
    )
    parser.add_argument(
        "--wake-word-dir",
        default=[_WAKEWORDS_DIR],
        action="append",
        help="Directory with wake word models (.tflite) and configs (.json)",
    )
    parser.add_argument(
        "--wake-model", default="okay_nabu", help="Id of active wake model"
    )
    parser.add_argument("--stop-model", default="stop", help="Id of stop model")
    parser.add_argument(
        "--download-dir",
        default=_REPO_DIR / "local",
        help="Directory to download custom wake word models, etc.",
    )
    parser.add_argument(
        "--refractory-seconds",
        default=2.0,
        type=float,
        help="Seconds before wake word can be activated again",
    )
    parser.add_argument(
        "--wakeup-sound", default=str(_SOUNDS_DIR / "wake_word_triggered.flac")
    )
    parser.add_argument(
        "--timer-finished-sound", default=str(_SOUNDS_DIR / "timer_finished.flac")
    )
    parser.add_argument("--preferences-file", default=_REPO_DIR / "preferences.json")
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Address for ESPHome server (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port", type=int, default=6053, help="Port for ESPHome server (default: 6053)"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Print DEBUG messages to console"
    )
    parser.add_argument(
        "--enable-reachy",
        action="store_true",
        help="Enable Reachy Mini integration",
    )
    args = parser.parse_args()

    # List devices and exit
    if args.list_input_devices:
        p = pyaudio.PyAudio()
        print("Input devices")
        print("=" * 13)
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info["maxInputChannels"] > 0:
                print(f"[{i}] {info['name']}")
        p.terminate()
        return

    if args.list_output_devices:
        p = pyaudio.PyAudio()
        print("Output devices")
        print("=" * 14)
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info["maxOutputChannels"] > 0:
                print(f"[{i}] {info['name']}")
        p.terminate()
        return

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    _LOGGER.debug(args)

    # Create directories
    args.download_dir = Path(args.download_dir)
    args.download_dir.mkdir(parents=True, exist_ok=True)

    # Initialize Reachy Mini integration
    reachy_integration = ReachyMiniIntegration()
    if args.enable_reachy:
        reachy_integration.connect()
    else:
        _LOGGER.info("Reachy Mini integration disabled")

    # Load available wake words
    wake_word_dirs = [Path(ww_dir) for ww_dir in args.wake_word_dir]
    wake_word_dirs.append(args.download_dir / "external_wake_words")
    available_wake_words: Dict[str, AvailableWakeWord] = {}

    for wake_word_dir in wake_word_dirs:
        if not wake_word_dir.exists():
            continue

        for model_config_path in wake_word_dir.glob("*.json"):
            model_id = model_config_path.stem
            if model_id == args.stop_model:
                continue

            try:
                with open(model_config_path, "r", encoding="utf-8") as model_config_file:
                    model_config = json.load(model_config_file)
                    model_type = WakeWordType(model_config.get("type", "microWakeWord"))
                    if model_type == WakeWordType.OPEN_WAKE_WORD:
                        wake_word_path = model_config_path.parent / model_config["model"]
                    else:
                        wake_word_path = model_config_path

                    available_wake_words[model_id] = AvailableWakeWord(
                        id=model_id,
                        type=WakeWordType(model_type),
                        wake_word=model_config["wake_word"],
                        trained_languages=model_config.get("trained_languages", []),
                        wake_word_path=wake_word_path,
                    )
            except Exception as e:
                _LOGGER.error("Error loading wake word config %s: %s", model_config_path, e)

    _LOGGER.debug("Available wake words: %s", list(sorted(available_wake_words.keys())))

    # Load preferences
    preferences_path = Path(args.preferences_file)
    if preferences_path.exists():
        try:
            with open(preferences_path, "r", encoding="utf-8") as preferences_file:
                preferences_dict = json.load(preferences_file)
                preferences = Preferences(**preferences_dict)
        except Exception as e:
            _LOGGER.error("Error loading preferences: %s", e)
            preferences = Preferences()
    else:
        preferences = Preferences()

    # Load wake/stop models
    active_wake_words: Set[str] = set()
    wake_models: Dict[str, Union[MicroWakeWord, OpenWakeWord]] = {}

    if preferences.active_wake_words:
        for wake_word_id in preferences.active_wake_words:
            wake_word = available_wake_words.get(wake_word_id)
            if wake_word is None:
                _LOGGER.warning("Unrecognized wake word id: %s", wake_word_id)
                continue

            try:
                _LOGGER.debug("Loading wake model: %s", wake_word_id)
                wake_models[wake_word_id] = wake_word.load()
                active_wake_words.add(wake_word_id)
            except Exception as e:
                _LOGGER.error("Error loading wake model %s: %s", wake_word_id, e)

    if not wake_models:
        wake_word_id = args.wake_model
        if wake_word_id in available_wake_words:
            try:
                wake_word = available_wake_words[wake_word_id]
                _LOGGER.debug("Loading wake model: %s", wake_word_id)
                wake_models[wake_word_id] = wake_word.load()
                active_wake_words.add(wake_word_id)
            except Exception as e:
                _LOGGER.error("Error loading default wake model: %s", e)
        else:
            _LOGGER.error("Default wake word not found: %s", wake_word_id)

    # Load stop model
    stop_model: Optional[MicroWakeWord] = None
    for wake_word_dir in wake_word_dirs:
        stop_config_path = wake_word_dir / f"{args.stop_model}.json"
        if not stop_config_path.exists():
            continue

        try:
            _LOGGER.debug("Loading stop model: %s", stop_config_path)
            stop_model = MicroWakeWord.from_config(stop_config_path)
            break
        except Exception as e:
            _LOGGER.error("Error loading stop model: %s", e)

    if stop_model is None:
        _LOGGER.warning("Stop model not loaded")

    # Create audio players
    music_player = AudioPlayer(device=args.audio_output_device)
    tts_player = AudioPlayer(device=args.audio_output_device)

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
        music_player=music_player,
        tts_player=tts_player,
        wakeup_sound=args.wakeup_sound,
        timer_finished_sound=args.timer_finished_sound,
        preferences=preferences,
        preferences_path=preferences_path,
        refractory_seconds=args.refractory_seconds,
        download_dir=args.download_dir,
        reachy_integration=reachy_integration,
    )

    # Start audio processing thread
    process_audio_thread = threading.Thread(
        target=process_audio,
        args=(state, args.audio_input_device),
        daemon=True,
    )
    process_audio_thread.start()

    # Start ESPHome server
    loop = asyncio.get_running_loop()
    server = await loop.create_server(
        lambda: VoiceSatelliteProtocol(state), host=args.host, port=args.port
    )

    # Auto discovery (zeroconf, mDNS)
    discovery = HomeAssistantZeroconf(port=args.port, name=args.name)
    await discovery.register_server()

    try:
        async with server:
            _LOGGER.info("Server started (host=%s, port=%s)", args.host, args.port)
            if reachy_integration.is_connected():
                _LOGGER.info("Reachy Mini integration enabled")
            await server.serve_forever()
    except KeyboardInterrupt:
        _LOGGER.info("Shutting down...")
    finally:
        state.audio_queue.put_nowait(None)
        process_audio_thread.join(timeout=5)
        if reachy_integration.is_connected():
            reachy_integration.disconnect()
        music_player.close()
        tts_player.close()
        await discovery.unregister_server()

    _LOGGER.debug("Server stopped")


def process_audio(state: ServerState, input_device: Optional[int]) -> None:
    """Process audio chunks from the microphone."""
    import pyaudio

    p = pyaudio.PyAudio()

    # Get input device
    if input_device is not None:
        device_index = input_device
    else:
        # Try to find default input device
        device_index = None
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info["maxInputChannels"] > 0 and info["isDefaultInputDevice"]:
                device_index = i
                break

        if device_index is None:
            _LOGGER.error("No default input device found")
            return

    device_info = p.get_device_info_by_index(device_index)
    _LOGGER.info(
        "Using audio input device: %s (index: %s)", device_info["name"], device_index
    )

    # Audio parameters
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000

    try:
        stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=CHUNK,
        )

        wake_words: List[Union[MicroWakeWord, OpenWakeWord]] = []
        micro_features: Optional[MicroWakeWordFeatures] = None
        micro_inputs: List[np.ndarray] = []

        oww_features: Optional[OpenWakeWordFeatures] = None
        oww_inputs: List[np.ndarray] = []
        has_oww = False

        last_active: Optional[float] = None

        _LOGGER.info("Audio processing started")

        while True:
            try:
                # Read audio chunk
                data = stream.read(CHUNK, exception_on_overflow=False)
                audio_array = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0

                # Send to satellite if connected
                if state.satellite is not None:
                    state.satellite.handle_audio(data)

                # Update wake word models
                if (not wake_words) or (state.wake_words_changed and state.wake_words):
                    state.wake_words_changed = False
                    wake_words = [
                        ww
                        for ww in state.wake_words.values()
                        if ww.id in state.active_wake_words
                    ]

                    has_oww = False
                    for wake_word in wake_words:
                        if isinstance(wake_word, OpenWakeWord):
                            has_oww = True

                    if micro_features is None:
                        micro_features = MicroWakeWordFeatures()

                    if has_oww and (oww_features is None):
                        oww_features = OpenWakeWordFeatures.from_builtin()

                # Process wake words
                if wake_words:
                    assert micro_features is not None
                    micro_inputs.clear()
                    micro_inputs.extend(micro_features.process_streaming(data))

                    if has_oww:
                        assert oww_features is not None
                        oww_inputs.clear()
                        oww_inputs.extend(oww_features.process_streaming(data))

                    for wake_word in wake_words:
                        activated = False
                        if isinstance(wake_word, MicroWakeWord):
                            for micro_input in micro_inputs:
                                if wake_word.process_streaming(micro_input):
                                    activated = True
                        elif isinstance(wake_word, OpenWakeWord):
                            for oww_input in oww_inputs:
                                for prob in wake_word.process_streaming(oww_input):
                                    if prob > 0.5:
                                        activated = True

                        if activated:
                            now = time.monotonic()
                            if (last_active is None) or (
                                (now - last_active) > state.refractory_seconds
                            ):
                                state.satellite.wakeup(wake_word)
                                if state.reachy_integration.is_connected():
                                    state.reachy_integration.on_wake_word_detected()
                                last_active = now

                    # Process stop word
                    if state.stop_word is not None:
                        stopped = False
                        for micro_input in micro_inputs:
                            if state.stop_word.process_streaming(micro_input):
                                stopped = True

                        if stopped and (state.stop_word.id in state.active_wake_words):
                            state.satellite.stop()
                            if state.reachy_integration.is_connected():
                                state.reachy_integration.on_stop()

            except Exception as e:
                _LOGGER.error("Error processing audio: %s", e)
                time.sleep(0.1)

    except Exception as e:
        _LOGGER.error("Error opening audio stream: %s", e)
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()
        _LOGGER.info("Audio processing stopped")


if __name__ == "__main__":
    asyncio.run(main())