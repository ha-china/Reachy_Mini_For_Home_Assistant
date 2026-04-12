import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


_CONFIG_PATH = Path("reachy_mini_home_assistant/animations/animation_config.py")
_CONFIG_SPEC = importlib.util.spec_from_file_location("test_animation_config_module", _CONFIG_PATH)
_CONFIG_MODULE = importlib.util.module_from_spec(_CONFIG_SPEC)
assert _CONFIG_SPEC is not None and _CONFIG_SPEC.loader is not None
_CONFIG_SPEC.loader.exec_module(_CONFIG_MODULE)
load_animation_config = _CONFIG_MODULE.load_animation_config
AnimationConfigError = _CONFIG_MODULE.AnimationConfigError


class AnimationConfigTests(unittest.TestCase):
    def test_valid_minimal_config_loads(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "conversation_animations.json"
            path.write_text(
                json.dumps(
                    {
                        "animations": {},
                        "emotions": {},
                        "settings": {},
                        "ha_event_behaviors": {"settings": {}, "mappings": {}},
                        "emotion_keywords": {"settings": {}, "keywords": {}},
                        "idle_random_actions": {"actions": []},
                    }
                ),
                encoding="utf-8",
            )
            data = load_animation_config(path)
            self.assertIn("animations", data)
            self.assertIn("ha_event_behaviors", data)

    def test_invalid_ha_event_section_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "conversation_animations.json"
            path.write_text(
                json.dumps(
                    {
                        "animations": {},
                        "emotions": {},
                        "settings": {},
                        "ha_event_behaviors": {"settings": [], "mappings": {}},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(AnimationConfigError):
                load_animation_config(path)
