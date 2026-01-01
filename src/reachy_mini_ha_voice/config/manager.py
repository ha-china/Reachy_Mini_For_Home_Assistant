"""
Configuration manager for Reachy Mini Voice Assistant
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manage application configuration"""
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self.config = self.load_config()
    
    def load_config(self) -> dict:
        """Load configuration from file"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                logger.info(f"Loaded configuration from {self.config_path}")
                return config
            except Exception as e:
                logger.error(f"Failed to load configuration: {e}")
                logger.info("Using default configuration")
                return self.get_default_config()
        else:
            logger.info("Configuration file not found, using defaults")
            return self.get_default_config()
    
    def save_config(self):
        """Save configuration to file"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved configuration to {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
            raise
    
    def get_default_config(self) -> dict:
        """Get default configuration"""
        return {
            "audio": {
                "input_device": None,
                "output_device": None,
                "sample_rate": 16000,
                "channels": 1,
                "block_size": 1024
            },
            "voice": {
                "wake_word": "okay_nabu",
                "wake_word_dirs": ["wakewords"]
            },
            "motion": {
                "enabled": True,
                "speech_reactive": True,
                "face_tracking": False
            },
            "esphome": {
                "host": "0.0.0.0",
                "port": 6053,
                "name": "Reachy Mini"
            },
            "robot": {
                "host": "localhost",
                "wireless": False
            },
            "logging": {
                "level": "INFO",
                "file": "reachy_mini_ha_voice.log"
            }
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key (supports nested keys with dots)"""
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, default)
            else:
                return default
        return value
    
    def set(self, key: str, value: Any):
        """Set configuration value by key (supports nested keys with dots)"""
        keys = key.split('.')
        config = self.config
        for k in keys[:-1]:
            config = config.setdefault(k, {})
        config[keys[-1]] = value
        self.save_config()
    
    def get_audio_config(self) -> dict:
        """Get audio configuration"""
        return self.get("audio", {})
    
    def get_voice_config(self) -> dict:
        """Get voice configuration"""
        return self.get("voice", {})
    
    def get_motion_config(self) -> dict:
        """Get motion configuration"""
        return self.get("motion", {})
    
    def get_esphome_config(self) -> dict:
        """Get ESPHome configuration"""
        return self.get("esphome", {})
    
    def get_robot_config(self) -> dict:
        """Get robot configuration"""
        return self.get("robot", {})
    
    def get_gradio_config(self) -> dict:
        """Get Gradio configuration"""
        return self.get("gradio", {})
    
    def update_audio_config(self, **kwargs):
        """Update audio configuration"""
        audio_config = self.config.setdefault("audio", {})
        audio_config.update(kwargs)
        self.save_config()
    
    def update_voice_config(self, **kwargs):
        """Update voice configuration"""
        voice_config = self.config.setdefault("voice", {})
        voice_config.update(kwargs)
        self.save_config()
    
    def update_motion_config(self, **kwargs):
        """Update motion configuration"""
        motion_config = self.config.setdefault("motion", {})
        motion_config.update(kwargs)
        self.save_config()
    
    def update_esphome_config(self, **kwargs):
        """Update ESPHome configuration"""
        esphome_config = self.config.setdefault("esphome", {})
        esphome_config.update(kwargs)
        self.save_config()
    
    def update_robot_config(self, **kwargs):
        """Update robot configuration"""
        robot_config = self.config.setdefault("robot", {})
        robot_config.update(kwargs)
        self.save_config()
    
    def update_gradio_config(self, **kwargs):
        """Update Gradio configuration"""
        gradio_config = self.config.setdefault("gradio", {})
        gradio_config.update(kwargs)
        self.save_config()