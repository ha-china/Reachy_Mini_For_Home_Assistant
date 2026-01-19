"""Emotion keyword detection from text responses.

This module provides automatic emotion detection based on keywords in LLM responses,
allowing the robot to express emotions naturally during conversation.
"""

import json
import logging
from pathlib import Path
from typing import Callable, Dict, Optional

_LOGGER = logging.getLogger(__name__)


class EmotionKeywordDetector:
    """Detects emotions from text using keyword matching.

    Loads keyword-to-emotion mappings from a JSON configuration file
    and provides automatic emotion detection for LLM responses.
    """

    def __init__(
        self,
        config_path: Optional[Path] = None,
        play_emotion_callback: Optional[Callable[[str], None]] = None,
    ):
        """Initialize the emotion detector.

        Args:
            config_path: Path to emotion_keywords.json. Defaults to animations folder.
            play_emotion_callback: Function to call when emotion is detected.
        """
        self._keywords: Dict[str, str] = {}
        self._enabled: bool = True
        self._play_emotion_callback = play_emotion_callback

        if config_path is None:
            config_path = Path(__file__).parent.parent / "animations" / "emotion_keywords.json"

        self._load_keywords(config_path)

    def _load_keywords(self, config_path: Path) -> None:
        """Load emotion keywords from JSON configuration file."""
        if not config_path.exists():
            _LOGGER.warning("Emotion keywords file not found: %s", config_path)
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._keywords = data.get("keywords", {})
            settings = data.get("settings", {})
            self._enabled = settings.get("enabled", True)

            _LOGGER.info(
                "Loaded %d emotion keywords (enabled=%s)",
                len(self._keywords),
                self._enabled
            )
        except Exception as e:
            _LOGGER.error("Failed to load emotion keywords: %s", e)

    def set_play_emotion_callback(self, callback: Callable[[str], None]) -> None:
        """Set the callback for playing emotions.

        Args:
            callback: Function that takes emotion name and plays it
        """
        self._play_emotion_callback = callback

    def detect_and_play(self, text: str) -> Optional[str]:
        """Detect emotion from text and trigger corresponding animation.

        Keywords are matched case-insensitively against the text.
        Only triggers one emotion per response (first match wins).

        Args:
            text: The text to analyze for emotional content

        Returns:
            The detected emotion name, or None if no emotion detected
        """
        if not text or not self._enabled:
            return None

        if not self._keywords:
            return None

        text_lower = text.lower()

        # Check each keyword pattern
        for keyword, emotion_name in self._keywords.items():
            if keyword.lower() in text_lower:
                _LOGGER.info(
                    "Auto-detected emotion '%s' from keyword '%s' in response",
                    emotion_name, keyword
                )
                if self._play_emotion_callback:
                    self._play_emotion_callback(emotion_name)
                return emotion_name

        _LOGGER.debug("No emotion keywords detected in response text")
        return None

    @property
    def enabled(self) -> bool:
        """Check if emotion detection is enabled."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Enable or disable emotion detection."""
        self._enabled = value

    @property
    def keyword_count(self) -> int:
        """Get the number of loaded keywords."""
        return len(self._keywords)
