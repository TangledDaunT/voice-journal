"""
Configuration management module for Voice Journal.
Handles loading, validating, and accessing configuration.
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, field

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings


class AudioConfig(BaseModel):
    sample_rate: int = 16000
    channels: int = 1
    block_size: int = 512
    ring_buffer_seconds: int = 30
    keep_audio: bool = False
    audio_storage_path: str = "./audio_clips"


class VADConfig(BaseModel):
    model_path: str = "./models/silero_vad.onnx"
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    min_segment_duration: float = Field(default=0.5, ge=0.0)
    silence_padding: float = Field(default=0.3, ge=0.0)
    max_segment_duration: float = Field(default=30.0, ge=1.0)


class SpeakerProfile(BaseModel):
    pitch_mean: float
    pitch_std: float
    spectral_centroid_mean: float
    spectral_centroid_std: float
    threshold_multiplier: float = 2.0


class SpeakerConfig(BaseModel):
    profiles: Dict[str, SpeakerProfile] = Field(default_factory=dict)
    calibration_file: str = "./config/voice_profiles.json"


class ASRConfig(BaseModel):
    model_size: str = Field(default="small")
    compute_type: str = Field(default="int8")
    device: str = Field(default="cpu")
    language: Optional[str] = None
    beam_size: int = Field(default=5, ge=1)
    vad_filter: bool = True

    @field_validator("model_size")
    @classmethod
    def validate_model_size(cls, v: str) -> str:
        valid_sizes = ["tiny", "base", "small", "medium", "large-v3"]
        if v not in valid_sizes:
            raise ValueError(f"model_size must be one of {valid_sizes}")
        return v

    @field_validator("compute_type")
    @classmethod
    def validate_compute_type(cls, v: str) -> str:
        valid_types = ["int8", "int16", "float16", "float32"]
        if v not in valid_types:
            raise ValueError(f"compute_type must be one of {valid_types}")
        return v


class ConversationConfig(BaseModel):
    gap_seconds: float = Field(default=90.0, ge=1.0)
    min_segments: int = Field(default=2, ge=1)
    unknown_voice_ratio_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    rapid_alternation_threshold: float = Field(default=3.0, ge=0.0)


class LLMConfig(BaseModel):
    model: str = Field(default="llama3.2:3b")
    ollama_host: str = Field(default="http://localhost:11434")
    timeout_seconds: int = Field(default=30, ge=5)
    max_retries: int = Field(default=1, ge=0)
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(default=500, ge=50)


class ObsidianConfig(BaseModel):
    vault_path: str = "./obsidian_vault"
    daily_notes_dir: str = "VoiceJournal/Daily"
    conversation_notes_dir: str = "VoiceJournal/Conversations"
    template_daily: Optional[str] = None
    template_conversation: Optional[str] = None


class DatabaseConfig(BaseModel):
    path: str = "./data/voice_journal.db"
    enable_fts: bool = True


class DaemonConfig(BaseModel):
    log_level: str = Field(default="INFO")
    log_file: str = "./logs/voice_journal.log"
    mute_file: str = "./data/mute_flag"
    health_check_interval: int = Field(default=60, ge=10)


class SystemConfig(BaseModel):
    notify_on_mute: bool = True
    hotkey_mute: str = "ctrl+shift+m"


class Config(BaseSettings):
    """Main configuration class."""
    audio: AudioConfig = Field(default_factory=AudioConfig)
    vad: VADConfig = Field(default_factory=VADConfig)
    speaker: SpeakerConfig = Field(default_factory=SpeakerConfig)
    asr: ASRConfig = Field(default_factory=ASRConfig)
    conversation: ConversationConfig = Field(default_factory=ConversationConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    obsidian: ObsidianConfig = Field(default_factory=ObsidianConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    daemon: DaemonConfig = Field(default_factory=DaemonConfig)
    system: SystemConfig = Field(default_factory=SystemConfig)

    model_config = {"env_prefix": "VJ_"}

    @classmethod
    def from_yaml(cls, path: str) -> "Config":
        """Load configuration from a YAML file."""
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        return cls(**data)

    def to_yaml(self, path: str) -> None:
        """Save configuration to a YAML file."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(self.model_dump(), f, default_flow_style=False)


def load_voice_profiles(path: str) -> Dict[str, SpeakerProfile]:
    """Load calibrated voice profiles from JSON file."""
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        data = json.load(f)
    return {k: SpeakerProfile(**v) for k, v in data.items()}


def save_voice_profiles(path: str, profiles: Dict[str, SpeakerProfile]) -> None:
    """Save calibrated voice profiles to JSON file."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(
            {k: v.model_dump() for k, v in profiles.items()},
            f,
            indent=2
        )
