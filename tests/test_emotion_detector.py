import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


_MODULE_PATH = Path("reachy_mini_home_assistant/entities/emotion_detector.py")
_SPEC = importlib.util.spec_from_file_location(
    "reachy_mini_home_assistant.entities.emotion_detector",
    _MODULE_PATH,
)
_MODULE = importlib.util.module_from_spec(_SPEC)
assert _SPEC is not None and _SPEC.loader is not None
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
EmotionKeywordDetector = _MODULE.EmotionKeywordDetector


class EmotionDetectorTests(unittest.TestCase):
    def test_loads_keywords_from_unified_behavior_section(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "conversation_animations.json"
            path.write_text(
                json.dumps(
                    {
                        "animations": {},
                        "emotions": {},
                        "settings": {},
                        "emotion_keywords": {
                            "keywords": {"great": "cheerful1", "sorry": "oops1"},
                            "settings": {"enabled": True},
                        },
                    }
                ),
                encoding="utf-8",
            )

            calls = []
            detector = EmotionKeywordDetector(config_path=path, play_emotion_callback=calls.append)

            self.assertEqual(detector.keyword_count, 2)
            self.assertTrue(detector.enabled)
            self.assertEqual(detector.detect_and_play("That is GREAT news"), "cheerful1")
            self.assertEqual(calls, ["cheerful1"])
