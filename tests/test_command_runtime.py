import re
import types
import unittest
from pathlib import Path

from reachy_mini_home_assistant.protocol import voice_pipeline


class CommandRuntimeSourceTests(unittest.TestCase):
    def test_non_idle_state_no_longer_resets_pose_anchor(self):
        path = Path("reachy_mini_home_assistant/motion/command_runtime.py")
        content = path.read_text(encoding="utf-8")

        match = re.search(r"if payload != RobotState\.IDLE:(?P<body>[\s\S]*?)logger\.debug", content)
        self.assertIsNotNone(match)
        body = match.group("body")

        self.assertNotIn("manager.state.target_yaw = 0.0", body)
        self.assertIn("Preserve the current pose anchor", body)
        self.assertIn("manager.state.target_pitch = 0.0", body)
        self.assertIn("manager.state.target_roll = 0.0", body)
        self.assertIn("manager.state.target_antenna_left = 0.0", body)
        self.assertIn("manager.state.target_antenna_right = 0.0", body)
        self.assertIn("old_state == RobotState.IDLE and not manager._idle_behavior_enabled()", body)


class VoicePipelineStopTests(unittest.TestCase):
    def _make_protocol(self):
        stop_word = types.SimpleNamespace(id="stop")
        tts_player = types.SimpleNamespace(stop=lambda: None)
        state = types.SimpleNamespace(stop_word=stop_word, active_wake_words={"stop"}, tts_player=tts_player)

        protocol = types.SimpleNamespace(
            _pipeline_active=True,
            _is_streaming_audio=True,
            _continue_conversation=True,
            _pending_voice_request=("wake", "conv"),
            _timer_finished=False,
            _timer_ring_start=123.0,
            _tts_url="http://example.test/tts",
            _tts_played=False,
            state=state,
        )
        protocol._set_stop_word_active_calls = []
        protocol._tts_finished_calls = 0
        protocol._set_stop_word_active = lambda active: protocol._set_stop_word_active_calls.append(active)
        protocol._tts_finished = lambda: setattr(protocol, "_tts_finished_calls", protocol._tts_finished_calls + 1)
        protocol.unduck = lambda: None
        return protocol

    def test_stop_tts_finishes_session_immediately(self):
        protocol = self._make_protocol()
        stop_calls = []
        protocol.state.tts_player.stop = lambda: stop_calls.append(True)

        voice_pipeline.stop(protocol)

        self.assertFalse(protocol._pipeline_active)
        self.assertFalse(protocol._is_streaming_audio)
        self.assertFalse(protocol._continue_conversation)
        self.assertIsNone(protocol._pending_voice_request)
        self.assertIsNone(protocol._tts_url)
        self.assertTrue(protocol._tts_played)
        self.assertNotIn(protocol.state.stop_word.id, protocol.state.active_wake_words)
        self.assertEqual(protocol._set_stop_word_active_calls, [False])
        self.assertEqual(len(stop_calls), 1)
        self.assertEqual(protocol._tts_finished_calls, 1)

    def test_stop_timer_sound_does_not_finish_tts_session(self):
        protocol = self._make_protocol()
        protocol._timer_finished = True
        protocol.state.active_wake_words.add(protocol.state.stop_word.id)
        stop_calls = []
        unduck_calls = []

        protocol.state.tts_player.stop = lambda: stop_calls.append(True)
        protocol.unduck = lambda: unduck_calls.append(True)

        voice_pipeline.stop(protocol)

        self.assertFalse(protocol._timer_finished)
        self.assertIsNone(protocol._timer_ring_start)
        self.assertEqual(len(unduck_calls), 1)
        self.assertEqual(len(stop_calls), 1)
        self.assertEqual(protocol._tts_finished_calls, 0)


class CommandRuntimeStateQueueTests(unittest.TestCase):
    def test_poll_commands_coalesces_back_to_back_state_updates(self):
        path = Path("reachy_mini_home_assistant/motion/command_runtime.py")
        content = path.read_text(encoding="utf-8")

        self.assertIn('if cmd == "set_state":', content)
        self.assertIn('if next_cmd == "set_state":', content)
        self.assertIn("payload = next_payload", content)


class IdleRestPoseSourceTests(unittest.TestCase):
    def test_transition_to_idle_rest_uses_full_rest_pose(self):
        path = Path("reachy_mini_home_assistant/motion/movement_manager.py")
        content = path.read_text(encoding="utf-8")

        self.assertIn("target_yaw=self._idle_rest_head_yaw_rad", content)
        self.assertIn("target_roll=self._idle_rest_head_roll_rad", content)
        self.assertIn("target_x=self._idle_rest_x_m", content)
        self.assertIn("target_y=self._idle_rest_y_m", content)
        self.assertIn("target_z=self._idle_rest_z_m", content)


class StopWordSourceTests(unittest.TestCase):
    def test_stop_word_uses_runtime_context_not_active_wakeword_membership(self):
        path = Path("reachy_mini_home_assistant/voice_assistant.py")
        content = path.read_text(encoding="utf-8")

        self.assertIn("stop_context_active = (", content)
        self.assertIn("self._state.tts_player.is_playing", content)
        self.assertIn("self._state.satellite._pipeline_active", content)
        self.assertIn("self._state.satellite._timer_finished", content)
        self.assertIn("self._state.active_wake_words.add(self._state.stop_word.id)", content)
        self.assertIn("self._state.stop_word.is_active = True", content)
        self.assertNotIn("stop_armed = self._state.stop_word.id in self._state.active_wake_words", content)
