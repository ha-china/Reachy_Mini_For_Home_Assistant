"""Shared loading and minimal validation for unified animation config."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class AnimationConfigError(ValueError):
    """Raised when the unified animation configuration is structurally invalid."""


_REQUIRED_TOP_LEVEL_TYPES: dict[str, type] = {
    "animations": dict,
    "emotions": dict,
    "settings": dict,
}

_OPTIONAL_TOP_LEVEL_TYPES: dict[str, type] = {
    "ha_event_behaviors": dict,
    "emotion_keywords": dict,
    "idle_random_actions": dict,
    "idle_rest_pose": dict,
}


def load_animation_config(config_path: Path) -> dict[str, Any]:
    """Load and minimally validate the unified animation config file."""
    if not config_path.exists():
        raise AnimationConfigError(f"Animation config file not found: {config_path}")

    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise AnimationConfigError(f"Failed to read animation config: {e}") from e

    if not isinstance(data, dict):
        raise AnimationConfigError("Animation config root must be an object")

    for key, expected_type in _REQUIRED_TOP_LEVEL_TYPES.items():
        value = data.get(key)
        if not isinstance(value, expected_type):
            raise AnimationConfigError(f"Animation config section '{key}' must be a {expected_type.__name__}")

    for key, expected_type in _OPTIONAL_TOP_LEVEL_TYPES.items():
        value = data.get(key)
        if value is not None and not isinstance(value, expected_type):
            raise AnimationConfigError(f"Animation config section '{key}' must be a {expected_type.__name__}")

    _validate_ha_event_behaviors(data.get("ha_event_behaviors"))
    _validate_emotion_keywords(data.get("emotion_keywords"))
    _validate_idle_random_actions(data.get("idle_random_actions"))

    return data


def get_animation_config_section(config_path: Path, section_name: str) -> dict[str, Any]:
    """Load one validated section from the unified animation config."""
    data = load_animation_config(config_path)
    section = data.get(section_name)
    if section is None:
        return {}
    if not isinstance(section, dict):
        raise AnimationConfigError(f"Animation config section '{section_name}' must be a dict")
    return section


def _validate_ha_event_behaviors(section: Any) -> None:
    if section is None:
        return
    mappings = section.get("mappings", {})
    if not isinstance(mappings, dict):
        raise AnimationConfigError("ha_event_behaviors.mappings must be a dict")
    settings = section.get("settings", {})
    if not isinstance(settings, dict):
        raise AnimationConfigError("ha_event_behaviors.settings must be a dict")


def _validate_emotion_keywords(section: Any) -> None:
    if section is None:
        return
    keywords = section.get("keywords", {})
    if not isinstance(keywords, dict):
        raise AnimationConfigError("emotion_keywords.keywords must be a dict")
    settings = section.get("settings", {})
    if not isinstance(settings, dict):
        raise AnimationConfigError("emotion_keywords.settings must be a dict")


def _validate_idle_random_actions(section: Any) -> None:
    if section is None:
        return
    actions = section.get("actions", [])
    if not isinstance(actions, list):
        raise AnimationConfigError("idle_random_actions.actions must be a list")
