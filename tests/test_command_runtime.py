import re
import unittest
from pathlib import Path


class CommandRuntimeSourceTests(unittest.TestCase):
    def test_non_idle_state_no_longer_resets_pose_anchor(self):
        path = Path("reachy_mini_home_assistant/motion/command_runtime.py")
        content = path.read_text(encoding="utf-8")

        match = re.search(r"if payload != RobotState\.IDLE:(?P<body>[\s\S]*?)logger\.debug", content)
        self.assertIsNotNone(match)
        body = match.group("body")

        self.assertNotIn("manager.state.target_yaw = 0.0", body)
        self.assertNotIn("manager.state.target_pitch = 0.0", body)
        self.assertNotIn("manager.state.target_roll = 0.0", body)
        self.assertIn("Preserve the current pose anchor", body)
