"""
ESPHome protocol for Reachy Mini Voice Assistant
"""

import asyncio
import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class VoiceAssistantEventType(Enum):
    """Voice assistant event types"""
    VOICE_ASSISTANT_START = 0
    VOICE_ASSISTANT_END = 1
    VOICE_ASSISTANT_ERROR = 2
    VOICE_ASSISTANT_STT_START = 3
    VOICE_ASSISTANT_STT_END = 4
    VOICE_ASSISTANT_TTS_START = 5
    VOICE_ASSISTANT_TTS_END = 6
    VOICE_ASSISTANT_INTENT_START = 7
    VOICE_ASSISTANT_INTENT_END = 8
    VOICE_ASSISTANT_WAKE_WORD_START = 9
    VOICE_ASSISTANT_WAKE_WORD_END = 10


class VoiceAssistantFeature(Enum):
    """Voice assistant features"""
    VOICE_ASSISTANT = 1
    API_AUDIO = 2
    ANNOUNCE = 4
    START_CONVERSATION = 8
    TIMERS = 16