"""Typed, validated configuration.

All settings come from environment variables (or a `.env` file). Nested groups
use a double underscore:  MQTT__USERNAME=...,  ALERTS__COOLDOWN_S=120.
Every value has a type and a range, so a typo fails at startup with a clear
message instead of misbehaving at 3 a.m.

See docs/CONFIGURATION.md for the full list.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from fall_detector.fall.fall_detector import FallThresholds
from fall_detector.runtime.retry import RetryPolicy

logger = logging.getLogger(__name__)


class MqttSettings(BaseModel):
    """Wearable (ESP32) fall messages from an MQTT broker."""

    enabled: bool = True
    host: str = "io.adafruit.com"
    port: int = Field(1883, ge=1, le=65535)
    topic: str = "tranhao/feeds/fall_alert"
    username: str | None = None
    password: SecretStr | None = None
    qos: int = Field(0, ge=0, le=2)  # 1 = at least once; check your broker supports it before raising
    keepalive_s: int = Field(60, ge=5)
    reconnect_min_s: float = Field(1.0, gt=0)
    reconnect_max_s: float = Field(60.0, gt=0)
    queue_size: int = Field(1000, ge=1)


class TelegramSettings(BaseModel):
    enabled: bool = True
    bot_token: SecretStr | None = None
    chat_id: str | None = None
    send_startup_message: bool = True


class AmiSettings(BaseModel):
    """Asterisk Manager Interface: phone call + SIP message to each extension."""

    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = Field(5038, ge=1, le=65535)
    username: str | None = None
    secret: SecretStr | None = None
    extensions: list[str] = Field(default_factory=lambda: ["6001", "6002", "6004"])
    caller_id: str = "FallAlertSystem <1000>"
    context: str = "internal"
    hangup_extension: str = "9999"  # dialplan point that plays the alert and hangs up
    cleanup_delay_s: float = Field(3.0, ge=0)  # pause after an alert so Asterisk can free channels


class CameraSettings(BaseModel):
    enabled: bool = True
    stream_url: str | None = None  # ESP32-CAM MJPEG stream, tried first when set
    webcam_indices: list[int] = Field(default_factory=lambda: [2, 0, 1])
    show_window: bool = True  # set False on servers / in Docker
    reconnect_delay_s: float = Field(2.0, gt=0)
    max_failed_reads: int = Field(50, ge=1)  # failed reads in a row before reopening the source

    def sources(self) -> list[str | int]:
        """Sources in priority order: stream URL first, then webcams."""
        sources: list[str | int] = [self.stream_url] if self.stream_url else []
        return sources + list(self.webcam_indices)


class VisionSettings(BaseModel):
    model_path: str = "yolov8n.pt"
    person_confidence_min: float = Field(0.5, ge=0, le=1)
    nms_iou_threshold: float = Field(0.7, ge=0, le=1)  # YOLO duplicate-box suppression
    track_iou_threshold: float = Field(0.7, ge=0, le=1)  # PersonTracker: same person if overlap above this
    pose_model_complexity: int = Field(1, ge=0, le=2)
    pose_min_detection_confidence: float = Field(0.5, ge=0, le=1)
    pose_min_tracking_confidence: float = Field(0.5, ge=0, le=1)


class FallSettings(BaseModel):
    """Mirrors FallThresholds; see fall/fall_detector.py for meaning."""

    tilt_threshold_deg: float = Field(60.0, gt=0, lt=180)
    lying_margin_deg: float = Field(10.0, ge=0)
    velocity_threshold_px: float = Field(0.5, ge=0)
    falling_frames: int = Field(5, ge=1)
    lying_frames: int = Field(5, ge=1)
    min_visibility: float = Field(0.5, ge=0, le=1)

    def thresholds(self) -> FallThresholds:
        return FallThresholds(**self.model_dump())


class AlertSettings(BaseModel):
    cooldown_s: float = Field(60.0, ge=0)  # per person/device, between two alerts
    forget_after_s: float = Field(30.0, gt=0)  # drop state of people/devices not seen for this long
    queue_size: int = Field(100, ge=1)
    workers: int = Field(2, ge=1)
    channel_timeout_s: float = Field(30.0, gt=0)  # one delivery attempt on one channel
    retry_attempts: int = Field(3, ge=1)
    retry_base_delay_s: float = Field(1.0, ge=0)
    shutdown_drain_s: float = Field(15.0, ge=0)  # time to finish queued alerts when stopping

    def retry_policy(self) -> RetryPolicy:
        return RetryPolicy(attempts=self.retry_attempts, base_delay_s=self.retry_base_delay_s)


class DatabaseSettings(BaseModel):
    path: Path = Path("fall_events.db")


class LoggingSettings(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    format: Literal["text", "json"] = "text"  # json for log collectors (Loki, ELK, CloudWatch)


class HealthSettings(BaseModel):
    enabled: bool = True
    host: str = "127.0.0.1"  # use 0.0.0.0 inside Docker
    port: int = Field(8080, ge=1, le=65535)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    mqtt: MqttSettings = MqttSettings()
    telegram: TelegramSettings = TelegramSettings()
    ami: AmiSettings = AmiSettings()
    camera: CameraSettings = CameraSettings()
    vision: VisionSettings = VisionSettings()
    fall: FallSettings = FallSettings()
    alerts: AlertSettings = AlertSettings()
    database: DatabaseSettings = DatabaseSettings()
    logging: LoggingSettings = LoggingSettings()
    health: HealthSettings = HealthSettings()

    @model_validator(mode="after")
    def _check_required_secrets(self) -> Settings:
        """Fail at startup if an enabled feature is missing its credentials."""
        missing = []
        if self.mqtt.enabled:
            missing += [
                f"MQTT__{n}"
                for n, v in (("USERNAME", self.mqtt.username), ("PASSWORD", self.mqtt.password))
                if not v
            ]
        if self.telegram.enabled:
            missing += [
                f"TELEGRAM__{n}"
                for n, v in (("BOT_TOKEN", self.telegram.bot_token), ("CHAT_ID", self.telegram.chat_id))
                if not v
            ]
        if self.ami.enabled:
            missing += [
                f"AMI__{n}"
                for n, v in (("USERNAME", self.ami.username), ("SECRET", self.ami.secret))
                if not v
            ]
        if missing:
            raise ValueError(
                "missing required settings for enabled features: "
                + ", ".join(missing)
                + " (set them in .env, or disable the feature, e.g. MQTT__ENABLED=false)"
            )
        if self.mqtt.reconnect_min_s > self.mqtt.reconnect_max_s:
            raise ValueError("MQTT__RECONNECT_MIN_S must not be greater than MQTT__RECONNECT_MAX_S")
        return self


# Old flat names from version 1 -> new nested names. Kept so an existing .env
# keeps working; a warning asks the user to rename.
LEGACY_ENV_NAMES = {
    "MQTT_USERNAME": "MQTT__USERNAME",
    "MQTT_PASSWORD": "MQTT__PASSWORD",
    "TELEGRAM_BOT_TOKEN": "TELEGRAM__BOT_TOKEN",
    "TELEGRAM_CHAT_ID": "TELEGRAM__CHAT_ID",
    "AMI_USERNAME": "AMI__USERNAME",
    "AMI_SECRET": "AMI__SECRET",
    "VIDEO_STREAM_URL": "CAMERA__STREAM_URL",
}


def apply_legacy_env_names(env_file: Path) -> list[str]:
    """Copy old variable names to the new ones when only the old one is set.

    Returns the old names that were used, so the caller can warn about them.
    """
    file_values = dotenv_values(env_file) if env_file.exists() else {}
    used = []
    for old, new in LEGACY_ENV_NAMES.items():
        value = os.environ.get(old) or file_values.get(old)
        if value and new not in os.environ and new not in file_values:
            os.environ[new] = value
            used.append(old)
    return used


def load_settings(env_file: Path | str = ".env") -> Settings:
    """Read settings from the environment and `env_file`. Raises ValidationError if invalid."""
    env_path = Path(env_file)
    legacy = apply_legacy_env_names(env_path)
    if legacy:
        logger.warning(
            "Deprecated setting names %s; rename them (see .env.example). They still work for now.",
            ", ".join(legacy),
        )
    return Settings(_env_file=env_path)
