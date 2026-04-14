from __future__ import annotations

import threading
import time

import numpy as np

from .audio_player_shared import STREAM_FETCH_CHUNK_SIZE, UNTHROTTLED_PREROLL_S, _LOGGER


class AudioPlayerStreamDecodedMixin:
    @staticmethod
    def _guess_gst_input_caps(content_type: str) -> str | None:
        ct = (content_type or "").split(";", 1)[0].strip().lower()
        mapping = {
            "audio/mpeg": "audio/mpeg,mpegversion=(int)1",
            "audio/mp3": "audio/mpeg,mpegversion=(int)1",
            "audio/aac": "audio/mpeg,mpegversion=(int)4,stream-format=(string)raw",
            "audio/mp4": "audio/mpeg,mpegversion=(int)4,stream-format=(string)raw",
            "audio/ogg": "application/ogg",
            "application/ogg": "application/ogg",
            "audio/opus": "audio/x-opus",
            "audio/webm": "video/webm",
            "audio/wav": "audio/x-wav",
            "audio/wave": "audio/x-wav",
            "audio/x-wav": "audio/x-wav",
            "audio/flac": "audio/x-flac",
            "audio/x-flac": "audio/x-flac",
        }
        return mapping.get(ct)

    def _stream_decoded_response(self, response, source_url: str, content_type: str) -> bool:
        try:
            import gi

            gi.require_version("Gst", "1.0")
            from gi.repository import Gst
        except Exception:
            return False
        try:
            Gst.init(None)
        except Exception:
            pass
        target_sr = self.reachy_mini.media.get_output_audio_samplerate()
        if target_sr <= 0:
            target_sr = 16000
        target_channels = 1
        if not self._ensure_media_playback_started():
            return False
        pipeline = Gst.Pipeline.new("tts_stream_decode")
        appsrc = Gst.ElementFactory.make("appsrc", "src")
        decodebin = Gst.ElementFactory.make("decodebin", "decode")
        audioconvert = Gst.ElementFactory.make("audioconvert", "conv")
        audioresample = Gst.ElementFactory.make("audioresample", "resample")
        capsfilter = Gst.ElementFactory.make("capsfilter", "caps")
        appsink = Gst.ElementFactory.make("appsink", "sink")
        if not all((pipeline, appsrc, decodebin, audioconvert, audioresample, capsfilter, appsink)):
            return False
        target_caps = Gst.Caps.from_string(f"audio/x-raw,format=S16LE,channels={target_channels},rate={target_sr}")
        capsfilter.set_property("caps", target_caps)
        appsrc.set_property("is-live", True)
        appsrc.set_property("format", Gst.Format.BYTES)
        appsrc.set_property("block", False)
        appsrc.set_property("do-timestamp", True)
        src_caps = self._guess_gst_input_caps(content_type)
        if src_caps:
            try:
                appsrc.set_property("caps", Gst.Caps.from_string(src_caps))
            except Exception:
                pass
        try:
            decodebin.set_property("caps", Gst.Caps.from_string("audio/x-raw"))
        except Exception:
            pass
        appsink.set_property("emit-signals", False)
        appsink.set_property("sync", False)
        appsink.set_property("max-buffers", 0)
        appsink.set_property("drop", False)
        pipeline.add(appsrc)
        pipeline.add(decodebin)
        pipeline.add(audioconvert)
        pipeline.add(audioresample)
        pipeline.add(capsfilter)
        pipeline.add(appsink)
        if (
            not appsrc.link(decodebin)
            or not audioconvert.link(audioresample)
            or not audioresample.link(capsfilter)
            or not capsfilter.link(appsink)
        ):
            return False
        audio_state = {"linked": False}

        def on_pad_added(_decodebin, pad) -> None:
            sink_pad = audioconvert.get_static_pad("sink")
            if sink_pad is None or sink_pad.is_linked():
                return
            caps_obj = pad.get_current_caps() or pad.query_caps(None)
            if caps_obj is None:
                return
            if caps_obj.to_string().startswith("audio/"):
                try:
                    result = pad.link(sink_pad)
                    if result == Gst.PadLinkReturn.OK:
                        audio_state["linked"] = True
                except Exception:
                    pass

        decodebin.connect("pad-added", on_pad_added)
        pushed_any = False
        played_frames = 0
        stream_start = time.monotonic()
        sway_ctx = self._init_stream_sway_context()
        bytes_per_frame = 2 * target_channels
        feed_done = threading.Event()
        decode_error = False

        def writer() -> None:
            try:
                for chunk in response.iter_content(chunk_size=STREAM_FETCH_CHUNK_SIZE):
                    if self._stop_flag.is_set():
                        break
                    if not chunk:
                        continue
                    gst_buffer = Gst.Buffer.new_allocate(None, len(chunk), None)
                    if gst_buffer is None:
                        continue
                    gst_buffer.fill(0, chunk)
                    ret = appsrc.emit("push-buffer", gst_buffer)
                    if ret not in (Gst.FlowReturn.OK, Gst.FlowReturn.FLUSHING):
                        _LOGGER.debug("appsrc push-buffer returned %s", ret)
                        break
            except Exception:
                pass
            finally:
                feed_done.set()
                try:
                    appsrc.emit("end-of-stream")
                except Exception:
                    pass

        try:
            state_ret = pipeline.set_state(Gst.State.PLAYING)
            if state_ret == Gst.StateChangeReturn.FAILURE:
                _LOGGER.debug("Failed to set GStreamer decode pipeline PLAYING for URL=%s", source_url)
                return False
            writer_thread = threading.Thread(target=writer, daemon=True)
            writer_thread.start()
            remainder = b""
            timeout_ns = 20_000_000
            bus = pipeline.get_bus()
            eos_seen = False
            eos_drain_empty_polls = 0
            while True:
                sample = appsink.emit("try-pull-sample", timeout_ns)
                if sample is not None:
                    eos_drain_empty_polls = 0
                    try:
                        gst_buffer = sample.get_buffer()
                        if gst_buffer is None:
                            continue
                        ok, map_info = gst_buffer.map(Gst.MapFlags.READ)
                        if not ok:
                            continue
                        try:
                            raw = bytes(map_info.data)
                        finally:
                            gst_buffer.unmap(map_info)
                        data = remainder + raw
                        usable_len = (len(data) // bytes_per_frame) * bytes_per_frame
                        remainder = data[usable_len:]
                        if usable_len == 0:
                            continue
                        pcm = np.frombuffer(data[:usable_len], dtype=np.int16).astype(np.float32) / 32768.0
                        pcm = np.clip(pcm * self._current_volume, -1.0, 1.0).reshape(-1, target_channels)
                        target_elapsed = played_frames / float(target_sr)
                        actual_elapsed = time.monotonic() - stream_start
                        if target_elapsed > UNTHROTTLED_PREROLL_S and target_elapsed > actual_elapsed:
                            time.sleep(min(0.05, target_elapsed - actual_elapsed))
                        if not self._push_audio_float(pcm):
                            continue
                        pushed_any = True
                        played_frames += int(pcm.shape[0])
                        self._feed_stream_sway(sway_ctx, pcm, target_sr)
                    finally:
                        sample = None
                elif eos_seen and feed_done.is_set():
                    eos_drain_empty_polls += 1
                msg = bus.timed_pop_filtered(0, Gst.MessageType.ERROR | Gst.MessageType.EOS)
                if msg is not None:
                    if msg.type == Gst.MessageType.EOS:
                        eos_seen = True
                    elif msg.type == Gst.MessageType.ERROR:
                        err, debug = msg.parse_error()
                        err_text = str(err).lower()
                        debug_text = str(debug).lower() if debug is not None else ""
                        if audio_state["linked"] and (
                            "not-linked" in err_text
                            or "not-linked" in debug_text
                            or "streaming stopped, reason not-linked" in debug_text
                        ):
                            continue
                        decode_error = True
                        _LOGGER.debug(
                            "GStreamer decode error content-type=%s url=%s err=%s debug=%s",
                            content_type or "unknown",
                            source_url,
                            err,
                            debug,
                        )
                        break
                if feed_done.is_set() and eos_seen:
                    sink_eos = False
                    try:
                        sink_eos = bool(appsink.is_eos())
                    except Exception:
                        sink_eos = False
                    if sink_eos and eos_drain_empty_polls >= 2:
                        break
                    if eos_drain_empty_polls >= 100:
                        break
                if self._stop_flag.is_set():
                    break
            writer_thread.join(timeout=1.0)
            if self._stop_flag.is_set():
                return True
            if decode_error:
                return False
            if pushed_any:
                return True
            completed_cleanly = feed_done.is_set() and eos_seen
            if not completed_cleanly:
                return False
        except Exception as e:
            _LOGGER.debug("Error during GStreamer stream decode: %s", e)
            pushed_any = False
        finally:
            self._finalize_stream_sway(sway_ctx)
            try:
                pipeline.set_state(Gst.State.NULL)
            except Exception:
                pass
        return pushed_any
