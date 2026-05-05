from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from .audio_player_shared import (
    MOVEMENT_LATENCY_S,
    SENDSPIN_HIGH_WATERMARK_BYTES,
    SENDSPIN_LATE_DROP_GRACE_US,
    SENDSPIN_LOCAL_BUFFER_CAPACITY_BYTES,
    SENDSPIN_SCHEDULE_AHEAD_LIMIT_US,
    SWAY_FRAME_DT_S,
    _LOGGER,
)

if TYPE_CHECKING:
    from aiosendspin.models.core import StreamStartMessage

try:
    from aiosendspin.client import SendspinClient
    from aiosendspin.client.client import AudioFormat, PCMFormat
    from aiosendspin.models.player import ClientHelloPlayerSupport, SupportedAudioFormat
    from aiosendspin.models.types import AudioCodec, PlayerCommand, Roles

    SENDSPIN_AVAILABLE = True
except Exception as e:
    SENDSPIN_AVAILABLE = False
    _LOGGER.warning("Sendspin unavailable, disabling integration: %s", e)
    PCMFormat = None  # type: ignore[assignment]
    AudioFormat = None  # type: ignore[assignment]
    SendspinClient = None  # type: ignore[assignment]
    ClientHelloPlayerSupport = None  # type: ignore[assignment]
    SupportedAudioFormat = None  # type: ignore[assignment]
    AudioCodec = None  # type: ignore[assignment]
    PlayerCommand = None  # type: ignore[assignment]
    Roles = None  # type: ignore[assignment]

try:
    from aiosendspin.client.listener import DEFAULT_PORT as SENDSPIN_DEFAULT_PORT
    from aiosendspin.client.listener import ClientListener
except Exception:
    ClientListener = None  # type: ignore[assignment]
    SENDSPIN_DEFAULT_PORT = 8928  # type: ignore[assignment]


@dataclass(slots=True)
class _QueuedSendspinChunk:
    play_time_us: int
    audio_float: np.ndarray
    byte_count: int


@dataclass(slots=True)
class _QueuedSendspinSwayFrame:
    target_time_us: int
    sway: dict[str, float]


class AudioPlayerSendspinMixin:
    @property
    def sendspin_available(self) -> bool:
        return SENDSPIN_AVAILABLE

    @property
    def sendspin_enabled(self) -> bool:
        return self._sendspin_enabled and self._sendspin_client is not None

    @property
    def sendspin_url(self) -> str | None:
        return self._sendspin_url

    def _get_sendspin_connect_lock(self) -> asyncio.Lock:
        if self._sendspin_connect_lock is None:
            self._sendspin_connect_lock = asyncio.Lock()
        return self._sendspin_connect_lock

    def _get_sendspin_effective_volume(self) -> float:
        if self._sendspin_muted:
            return 0.0
        return self._current_volume * (self._sendspin_remote_volume / 100.0)

    def _ensure_sendspin_worker(self) -> None:
        if self._sendspin_queue_thread is not None and self._sendspin_queue_thread.is_alive():
            return
        self._sendspin_queue_stop.clear()
        self._sendspin_queue_event.clear()
        self._sendspin_queue_thread = threading.Thread(
            target=self._sendspin_worker_loop, name="sendspin-playback", daemon=True
        )
        self._sendspin_queue_thread.start()

    def _stop_sendspin_worker(self) -> None:
        self._sendspin_queue_stop.set()
        self._sendspin_queue_event.set()
        if self._sendspin_queue_thread is not None:
            try:
                self._sendspin_queue_thread.join(timeout=1.0)
            except Exception:
                pass
            self._sendspin_queue_thread = None
        self._sendspin_queue_stop.clear()
        self._sendspin_queue_event.clear()

    def _sendspin_worker_loop(self) -> None:
        while not self._sendspin_queue_stop.is_set():
            if self._sendspin_paused:
                self._sendspin_queue_event.wait(timeout=0.05)
                self._sendspin_queue_event.clear()
                continue
            with self._sendspin_queue_lock:
                chunk = self._sendspin_queue[0] if self._sendspin_queue else None
                sway_frame = self._sendspin_sway_queue[0] if self._sendspin_sway_queue else None
            if chunk is None and sway_frame is None:
                self._sendspin_queue_event.wait(timeout=0.1)
                self._sendspin_queue_event.clear()
                continue
            now_us = time.monotonic_ns() // 1000
            next_audio_us = chunk.play_time_us if chunk is not None else None
            next_sway_us = sway_frame.target_time_us if sway_frame is not None else None
            next_event_us = min(ts for ts in (next_audio_us, next_sway_us) if ts is not None)
            delay_us = next_event_us - now_us
            if delay_us > 2_000:
                self._sendspin_queue_event.wait(timeout=min(delay_us / 1_000_000.0, 0.05))
                self._sendspin_queue_event.clear()
                continue
            handle_sway = False
            with self._sendspin_queue_lock:
                chunk = self._sendspin_queue[0] if self._sendspin_queue else None
                sway_frame = self._sendspin_sway_queue[0] if self._sendspin_sway_queue else None
                now_us = time.monotonic_ns() // 1000
                next_audio_us = chunk.play_time_us if chunk is not None else None
                next_sway_us = sway_frame.target_time_us if sway_frame is not None else None
                if next_audio_us is None and next_sway_us is None:
                    continue
                if next_audio_us is None:
                    handle_sway = True
                elif next_sway_us is None:
                    handle_sway = False
                else:
                    handle_sway = next_sway_us < next_audio_us
                if handle_sway:
                    sway_frame = self._sendspin_sway_queue.popleft()
                else:
                    chunk = self._sendspin_queue.popleft()
                    self._sendspin_queue_bytes = max(0, self._sendspin_queue_bytes - chunk.byte_count)
            if handle_sway:
                self._apply_sendspin_sway_frame(sway_frame)
                continue
            late_by_us = now_us - chunk.play_time_us
            if late_by_us > SENDSPIN_LATE_DROP_GRACE_US:
                _LOGGER.debug("Dropping late Sendspin chunk (%d ms late)", late_by_us // 1000)
                continue
            self._push_sendspin_audio_sample(chunk.audio_float)

    def _apply_sendspin_sway_frame(self, sway_frame: _QueuedSendspinSwayFrame) -> None:
        if self._sway_callback is None or self._sendspin_paused:
            return
        try:
            self._sway_callback(sway_frame.sway)
        except Exception:
            _LOGGER.debug("Failed to apply Sendspin sway frame", exc_info=True)

    def _push_sendspin_audio_sample(self, audio_float: np.ndarray) -> None:
        if self.reachy_mini is None:
            return
        if not self._sendspin_playback_started:
            try:
                self.reachy_mini.media.start_playing()
                self._sendspin_playback_started = True
            except Exception:
                _LOGGER.exception("Failed to start media playback for Sendspin")
                return
        acquired = self._gstreamer_lock.acquire(timeout=0.05)
        if not acquired:
            _LOGGER.debug("GStreamer lock busy, dropping due Sendspin chunk")
            return
        try:
            self.reachy_mini.media.push_audio_sample(audio_float)
        except Exception:
            _LOGGER.exception("Failed to push Sendspin audio chunk")
        finally:
            self._gstreamer_lock.release()

    def _stop_sendspin_output(self) -> None:
        if self.reachy_mini is None:
            return
        try:
            self.reachy_mini.media.audio.clear_output_buffer()
        except Exception:
            _LOGGER.debug("Failed to clear output buffer", exc_info=True)
        if self._sendspin_playback_started:
            try:
                self.reachy_mini.media.stop_playing()
            except Exception:
                _LOGGER.debug("Failed to stop Sendspin playback", exc_info=True)
        self._sendspin_playback_started = False

    def _clear_sendspin_queue(self) -> None:
        with self._sendspin_queue_lock:
            self._sendspin_queue.clear()
            self._sendspin_queue_bytes = 0
            self._sendspin_sway_queue.clear()
        self._sendspin_queue_event.set()

    def _reset_sendspin_sway_state(self, *, reset_output: bool) -> None:
        self._sendspin_sway_state = None
        if reset_output:
            self._reset_sway_output()

    def _reset_sendspin_stream_state(self, *, stop_output: bool) -> None:
        self._clear_sendspin_queue()
        self._reset_sendspin_sway_state(reset_output=True)
        self._sendspin_audio_format = None
        self._logged_resample = False
        if stop_output:
            self._stop_sendspin_output()

    def _queue_sendspin_audio(self, play_time_us: int, audio_float: np.ndarray, byte_count: int) -> None:
        with self._sendspin_queue_lock:
            self._sendspin_queue.append(_QueuedSendspinChunk(play_time_us, audio_float, byte_count))
            self._sendspin_queue_bytes += byte_count
            while self._sendspin_queue_bytes > SENDSPIN_LOCAL_BUFFER_CAPACITY_BYTES and self._sendspin_queue:
                dropped = self._sendspin_queue.popleft()
                self._sendspin_queue_bytes = max(0, self._sendspin_queue_bytes - dropped.byte_count)
                now = time.monotonic()
                if now - getattr(self, "_last_sendspin_overflow_log", 0.0) >= 1.0:
                    _LOGGER.warning("Sendspin buffer overflow, dropping oldest queued audio")
                    self._last_sendspin_overflow_log = now
        self._sendspin_queue_event.set()

    def _should_backpressure_sendspin_chunk(self, play_time_us: int, byte_count: int) -> bool:
        with self._sendspin_queue_lock:
            queued_bytes = self._sendspin_queue_bytes
        if queued_bytes + byte_count < SENDSPIN_HIGH_WATERMARK_BYTES:
            return False

        now_us = time.monotonic_ns() // 1000
        queued_ahead_us = max(0, play_time_us - now_us)
        if queued_ahead_us < 500_000:
            return False

        now = time.monotonic()
        if now - getattr(self, "_last_sendspin_overflow_log", 0.0) >= 1.0:
            _LOGGER.warning(
                "Sendspin backpressure active, skipping queued audio (queued=%d bytes, ahead=%d ms)",
                queued_bytes,
                queued_ahead_us // 1000,
            )
            self._last_sendspin_overflow_log = now
        return True

    def _get_sendspin_sway_state(self) -> dict | None:
        if self._sway_callback is None:
            return None
        if self._sendspin_sway_state is None:
            analyzer = self._new_sway_analyzer()
            if analyzer is None:
                _LOGGER.debug("Failed to initialize Sendspin sway analyzer")
                self._sendspin_sway_state = None
            else:
                self._sendspin_sway_state = {"sway": analyzer}
        return self._sendspin_sway_state

    def _queue_sendspin_sway(self, play_time_us: int, pcm: np.ndarray, sample_rate: int) -> None:
        ctx = self._get_sendspin_sway_state()
        if ctx is None:
            return
        try:
            results = self._compute_sway_frames(ctx["sway"], pcm, sample_rate)
            if not results:
                return
            latency_us = int(MOVEMENT_LATENCY_S * 1_000_000)
            hop_us = int(SWAY_FRAME_DT_S * 1_000_000)
            with self._sendspin_queue_lock:
                for idx, item in enumerate(results):
                    self._sendspin_sway_queue.append(
                        _QueuedSendspinSwayFrame(target_time_us=play_time_us + latency_us + idx * hop_us, sway=item)
                    )
        except Exception:
            _LOGGER.debug("Failed to queue Sendspin sway frames", exc_info=True)
        self._sendspin_queue_event.set()

    def _decode_pcm_bytes(self, audio_data: bytes, pcm_format: PCMFormat) -> np.ndarray:
        if pcm_format.bit_depth == 16:
            audio_int = np.frombuffer(audio_data, dtype="<i2")
            audio_float = audio_int.astype(np.float32) / 32768.0
        elif pcm_format.bit_depth == 24:
            raw = np.frombuffer(audio_data, dtype=np.uint8)
            frame_count = len(raw) // 3
            raw = raw[: frame_count * 3].reshape(-1, 3)
            audio_int = (
                raw[:, 0].astype(np.int32) | (raw[:, 1].astype(np.int32) << 8) | (raw[:, 2].astype(np.int32) << 16)
            )
            sign_mask = 1 << 23
            audio_int = (audio_int ^ sign_mask) - sign_mask
            audio_float = audio_int.astype(np.float32) / 8388608.0
        elif pcm_format.bit_depth == 32:
            audio_int = np.frombuffer(audio_data, dtype="<i4")
            audio_float = audio_int.astype(np.float32) / 2147483648.0
        else:
            raise ValueError(f"Unsupported PCM bit depth: {pcm_format.bit_depth}")
        audio_float = np.clip(audio_float, -1.0, 1.0)
        channels = max(1, int(pcm_format.channels))
        frame_count = len(audio_float) // channels
        if frame_count <= 0:
            raise ValueError("Audio chunk does not contain a complete frame")
        return audio_float[: frame_count * channels].reshape(frame_count, channels)

    def _decode_sendspin_audio(self, audio_data: bytes, fmt: AudioFormat) -> np.ndarray:
        if fmt.codec != AudioCodec.PCM:
            raise ValueError(f"Unsupported Sendspin codec for Reachy playback: {fmt.codec.value}")
        pcm_format = fmt.pcm_format
        audio_float = self._decode_pcm_bytes(audio_data, pcm_format)
        target_sample_rate = self.reachy_mini.media.get_output_audio_samplerate()
        if pcm_format.sample_rate != target_sample_rate and target_sample_rate > 0:
            import scipy.signal

            new_length = int(len(audio_float) * target_sample_rate / pcm_format.sample_rate)
            if new_length > 0:
                audio_float = scipy.signal.resample(audio_float, new_length, axis=0)
                if not self._logged_resample:
                    _LOGGER.debug(
                        "Resampling Sendspin audio: %d Hz -> %d Hz", pcm_format.sample_rate, target_sample_rate
                    )
                    self._logged_resample = True
        return np.clip(audio_float * self._get_sendspin_effective_volume(), -1.0, 1.0).astype(np.float32, copy=False)

    def _build_sendspin_client(self) -> SendspinClient:
        player_support = ClientHelloPlayerSupport(
            supported_formats=[
                SupportedAudioFormat(codec=AudioCodec.PCM, channels=2, sample_rate=16000, bit_depth=16),
                SupportedAudioFormat(codec=AudioCodec.PCM, channels=1, sample_rate=16000, bit_depth=16),
                SupportedAudioFormat(codec=AudioCodec.PCM, channels=2, sample_rate=48000, bit_depth=16),
                SupportedAudioFormat(codec=AudioCodec.PCM, channels=2, sample_rate=44100, bit_depth=16),
                SupportedAudioFormat(codec=AudioCodec.PCM, channels=1, sample_rate=48000, bit_depth=16),
                SupportedAudioFormat(codec=AudioCodec.PCM, channels=1, sample_rate=44100, bit_depth=16),
            ],
            buffer_capacity=32_000_000,
            supported_commands=[PlayerCommand.VOLUME, PlayerCommand.MUTE],
        )
        return SendspinClient(
            client_id=self._sendspin_client_id,
            client_name="Reachy Mini",
            roles=[Roles.PLAYER],
            player_support=player_support,
            initial_volume=max(0, min(100, round(self._unduck_volume * 100.0))),
            initial_muted=self._sendspin_muted,
        )

    def _remove_sendspin_listeners(self) -> None:
        for unsub in self._sendspin_unsubscribers:
            try:
                unsub()
            except Exception:
                _LOGGER.debug("Error during Sendspin unsubscribe", exc_info=True)
        self._sendspin_unsubscribers.clear()

    def _register_sendspin_listeners(self, client: SendspinClient) -> None:
        def _is_current() -> bool:
            return self._sendspin_client is client

        def _handle_audio_chunk(ts: int, audio_data: bytes, fmt: AudioFormat) -> None:
            if _is_current():
                self._on_sendspin_audio_chunk(client, ts, audio_data, fmt)

        def _handle_stream_start(message: StreamStartMessage) -> None:
            if _is_current():
                self._on_sendspin_stream_start(client, message)

        def _handle_stream_end(roles: list[str] | None) -> None:
            if _is_current():
                self._on_sendspin_stream_end(client, roles)

        def _handle_stream_clear(roles: list[str] | None) -> None:
            if _is_current():
                self._on_sendspin_stream_clear(client, roles)

        def _handle_disconnect() -> None:
            if _is_current():
                self._on_sendspin_disconnected(client)

        def _handle_server_command(payload) -> None:
            if _is_current():
                self._on_sendspin_server_command(client, payload)

        self._sendspin_unsubscribers = [
            client.add_audio_chunk_listener(_handle_audio_chunk),
            client.add_stream_start_listener(_handle_stream_start),
            client.add_stream_end_listener(_handle_stream_end),
            client.add_stream_clear_listener(_handle_stream_clear),
            client.add_disconnect_listener(_handle_disconnect),
            client.add_server_command_listener(_handle_server_command),
        ]

    def _activate_sendspin_client(self, client: SendspinClient, *, server_url: str | None) -> None:
        self._remove_sendspin_listeners()
        self._sendspin_client = client
        self._sendspin_url = server_url
        self._sendspin_enabled = True
        self._sendspin_remote_volume = max(0, min(100, round(self._unduck_volume * 100.0)))
        self._register_sendspin_listeners(client)
        self._ensure_sendspin_worker()

    def _on_sendspin_disconnected(self, client: SendspinClient) -> None:
        if self._sendspin_client is not client:
            return
        _LOGGER.info("Sendspin disconnected")
        self._remove_sendspin_listeners()
        self._sendspin_enabled = False
        self._sendspin_client = None
        self._sendspin_url = None
        self._sendspin_stream_active = False
        self._reset_sendspin_stream_state(stop_output=True)

    def pause_sendspin(self) -> None:
        if self._sendspin_paused and not self._sendspin_stream_active:
            return
        self._sendspin_paused = True
        self._reset_sendspin_stream_state(stop_output=True)
        _LOGGER.debug("Sendspin audio paused (voice assistant active)")

    def resume_sendspin(self) -> None:
        if not self._sendspin_paused:
            return
        self._sendspin_paused = False
        self._sendspin_queue_event.set()
        _LOGGER.debug("Sendspin audio resumed")

    async def _start_sendspin_listener(self) -> None:
        if ClientListener is None:
            return
        if self._sendspin_listener is not None:
            return
        self._sendspin_listener = ClientListener(
            client_id=self._sendspin_client_id,
            client_name="Reachy Mini",
            port=SENDSPIN_DEFAULT_PORT,
            on_connection=self._handle_sendspin_listener_connection,
        )
        try:
            await self._sendspin_listener.start()
        except Exception:
            self._sendspin_listener = None
            raise
        _LOGGER.info("Sendspin listener started on port %d", self._sendspin_listener.port)

    async def _handle_sendspin_listener_connection(self, ws) -> None:
        if not SENDSPIN_AVAILABLE:
            await ws.close()
            return
        disconnect_event = asyncio.Event()
        client = self._build_sendspin_client()
        async with self._get_sendspin_connect_lock():
            if self._sendspin_client is not None:
                await self._disconnect_sendspin()
            self._activate_sendspin_client(client, server_url=None)

        def _on_disconnect() -> None:
            disconnect_event.set()

        disconnect_unsub = client.add_disconnect_listener(_on_disconnect)
        try:
            await client.attach_websocket(ws)
            _LOGGER.info("Accepted incoming Sendspin connection")
            await disconnect_event.wait()
        except Exception:
            _LOGGER.exception("Failed to attach incoming Sendspin websocket")
            async with self._get_sendspin_connect_lock():
                if self._sendspin_client is client:
                    await self._disconnect_sendspin()
            raise
        finally:
            try:
                disconnect_unsub()
            except Exception:
                _LOGGER.debug("Failed to remove temporary Sendspin disconnect listener", exc_info=True)

    async def start_sendspin_discovery(self) -> None:
        if not SENDSPIN_AVAILABLE:
            _LOGGER.debug("aiosendspin not installed, skipping Sendspin discovery")
            return
        if self._sendspin_discovery is not None and self._sendspin_discovery.is_running:
            _LOGGER.debug("Sendspin discovery already running")
            return
        from ..protocol.zeroconf import SendspinDiscovery

        _LOGGER.info("Starting Sendspin server discovery...")
        self._sendspin_discovery = SendspinDiscovery(self._on_sendspin_server_found, self._on_sendspin_server_removed)
        await self._sendspin_discovery.start()
        self._ensure_sendspin_worker()
        try:
            await self._start_sendspin_listener()
        except Exception:
            _LOGGER.warning(
                "Sendspin incoming listener unavailable; continuing with discovery/client mode", exc_info=True
            )

    async def _on_sendspin_server_found(self, server_url: str) -> None:
        await self._connect_to_server(server_url)

    async def _on_sendspin_server_removed(self, server_url: str) -> None:
        if self._sendspin_url == server_url:
            _LOGGER.info("Active Sendspin server disappeared: %s", server_url)
            await self._disconnect_sendspin()

    async def _connect_to_server(self, server_url: str) -> bool:
        if not SENDSPIN_AVAILABLE:
            return False
        async with self._get_sendspin_connect_lock():
            if self._sendspin_enabled and self._sendspin_url == server_url and self._sendspin_client is not None:
                return True
            if self._sendspin_client is not None:
                await self._disconnect_sendspin()
            client = self._build_sendspin_client()
            try:
                await client.connect(server_url)
            except Exception:
                _LOGGER.exception("Failed to connect to Sendspin server %s", server_url)
                try:
                    await client.disconnect()
                except Exception:
                    _LOGGER.debug("Failed to clean up Sendspin client after connect error", exc_info=True)
                return False
            self._activate_sendspin_client(client, server_url=server_url)
            _LOGGER.info("Sendspin connected as PLAYER: %s (client_id=%s)", server_url, self._sendspin_client_id)
            return True

    def _on_sendspin_audio_chunk(
        self, client: SendspinClient, server_timestamp_us: int, audio_data: bytes, fmt: AudioFormat
    ) -> None:
        if self._sendspin_client is not client or self._sendspin_paused or self.reachy_mini is None:
            return
        try:
            play_time_us = int(client.compute_play_time(server_timestamp_us))
            now_us = time.monotonic_ns() // 1000
            play_time_us = min(play_time_us, now_us + SENDSPIN_SCHEDULE_AHEAD_LIMIT_US)
            if self._should_backpressure_sendspin_chunk(play_time_us, len(audio_data)):
                return

            self._sendspin_audio_format = fmt
            audio_float = self._decode_sendspin_audio(audio_data, fmt)
            sway_sample_rate = self.reachy_mini.media.get_output_audio_samplerate()
            if sway_sample_rate <= 0:
                sway_sample_rate = fmt.pcm_format.sample_rate
            self._queue_sendspin_audio(play_time_us, audio_float, len(audio_data))
            self._queue_sendspin_sway(play_time_us, audio_float, sway_sample_rate)
        except Exception:
            _LOGGER.exception("Error handling Sendspin audio chunk")

    def _on_sendspin_stream_start(self, client: SendspinClient, message: StreamStartMessage) -> None:
        if self._sendspin_client is not client:
            return
        self._sendspin_stream_active = True
        self._reset_sendspin_stream_state(stop_output=True)
        player = getattr(message.payload, "player", None)
        if player is None:
            _LOGGER.debug("Sendspin stream started without player payload")
            return
        _LOGGER.info(
            "Sendspin stream started: codec=%s sample_rate=%s channels=%s bit_depth=%s",
            getattr(player.codec, "value", player.codec),
            player.sample_rate,
            player.channels,
            player.bit_depth,
        )

    def _on_sendspin_stream_end(self, client: SendspinClient, roles: list[str] | None) -> None:
        if self._sendspin_client is not client:
            return
        if roles is None or "player" in roles:
            self._sendspin_stream_active = False
            self._reset_sendspin_stream_state(stop_output=True)
            _LOGGER.debug("Sendspin stream ended")

    def _on_sendspin_stream_clear(self, client: SendspinClient, roles: list[str] | None) -> None:
        if self._sendspin_client is not client:
            return
        if roles is None or "player" in roles:
            _LOGGER.debug("Sendspin stream cleared")
            self._reset_sendspin_stream_state(stop_output=True)

    def _on_sendspin_server_command(self, client: SendspinClient, payload) -> None:
        if self._sendspin_client is not client:
            return
        player_payload = getattr(payload, "player", None)
        if player_payload is None:
            return
        try:
            if player_payload.command == PlayerCommand.VOLUME and player_payload.volume is not None:
                self._sendspin_remote_volume = max(0, min(100, int(player_payload.volume)))
                _LOGGER.debug("Sendspin remote volume set to %d", self._sendspin_remote_volume)
            elif player_payload.command == PlayerCommand.MUTE and player_payload.mute is not None:
                self._sendspin_muted = bool(player_payload.mute)
                if self._sendspin_muted:
                    self._reset_sendspin_stream_state(stop_output=True)
                _LOGGER.debug("Sendspin remote mute set to %s", self._sendspin_muted)
        except Exception:
            _LOGGER.exception("Failed to handle Sendspin server command")

    async def _disconnect_sendspin(self) -> None:
        client = self._sendspin_client
        self._remove_sendspin_listeners()
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                _LOGGER.debug("Error disconnecting from Sendspin", exc_info=True)
        self._sendspin_client = None
        self._sendspin_enabled = False
        self._sendspin_url = None
        self._sendspin_stream_active = False
        self._reset_sendspin_stream_state(stop_output=True)

    async def stop_sendspin(self) -> None:
        if self._sendspin_discovery is not None:
            await self._sendspin_discovery.stop()
            self._sendspin_discovery = None
        if self._sendspin_listener is not None:
            await self._sendspin_listener.stop()
            self._sendspin_listener = None
        await self._disconnect_sendspin()
        self._sendspin_client = None
        self._sendspin_url = None
        self._sendspin_audio_format = None
        self._sendspin_enabled = False
        self._sendspin_stream_active = False
        self._sendspin_paused = False
        self._sendspin_muted = False
        self._sendspin_remote_volume = 100
        self._stop_sendspin_worker()
        _LOGGER.info("Sendspin stopped")
