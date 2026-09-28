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

    enabled: bool = Field(True, description="Listen for wearable fall messages")
    host: str = Field("io.adafruit.com", description="Broker host name")
    port: int = Field(1883, ge=1, le=65535, description="Broker port")
    topic: str = Field("tranhao/feeds/fall_alert", description="Topic the wearable publishes to")
    username: str | None = Field(None, description="Broker user (required when enabled)")
    password: SecretStr | None = Field(None, description="Broker password or key (required when enabled)")
    qos: int = Field(0, ge=0, le=2, description="Subscribe QoS; 1 = at least once, if the broker supports it")
    keepalive_s: int = Field(60, ge=5, description="Ping interval that detects a dead connection")
    reconnect_min_s: float = Field(1.0, gt=0, description="First wait after a disconnect; doubles each try")
    reconnect_max_s: float = Field(60.0, gt=0, description="Longest wait between reconnect tries")
    queue_size: int = Field(1000, ge=1, description="Messages buffered between network and processing")


class TelegramSettings(BaseModel):
    enabled: bool = Field(True, description="Send alerts to Telegram")
    bot_token: SecretStr | None = Field(None, description="Token from @BotFather (required when enabled)")
    chat_id: str | None = Field(
        None, description="Chat to alert; see scripts/get_telegram_chat_id.py (required when enabled)"
    )
    send_startup_message: bool = Field(True, description="Send a message when the system starts")


class AmiSettings(BaseModel):
    """Asterisk Manager Interface: phone call + SIP message to each extension."""

    enabled: bool = Field(True, description="Call and message SIP phones through Asterisk")
    host: str = Field("127.0.0.1", description="Asterisk host")
    port: int = Field(5038, ge=1, le=65535, description="AMI port")
    username: str | None = Field(None, description="AMI user from manager.conf (required when enabled)")
    secret: SecretStr | None = Field(None, description="AMI secret (required when enabled)")
    extensions: list[str] = Field(
        default_factory=lambda: ["6001", "6002", "6004"], description="SIP extensions to alert (JSON list)"
    )
    caller_id: str = Field("FallAlertSystem <1000>", description="Caller id shown on the phones")
    context: str = Field("internal", description="Dialplan context for the call")
    hangup_extension: str = Field("9999", description="Dialplan extension that plays the alert and hangs up")
    cleanup_delay_s: float = Field(
        3.0, ge=0, description="Pause after an alert so Asterisk can free channels"
    )


class CameraSettings(BaseModel):
    enabled: bool = Field(True, description="Run camera-based detection (loads the vision models)")
    stream_url: str | None = Field(None, description="ESP32-CAM MJPEG stream URL, tried before webcams")
    webcam_indices: list[int] = Field(
        default_factory=lambda: [2, 0, 1], description="Webcam indices to try, in order (JSON list)"
    )
    show_window: bool = Field(True, description="Show the video window; false on servers and in Docker")
    reconnect_delay_s: float = Field(2.0, gt=0, description="Wait before reopening a lost or missing source")
    max_failed_reads: int = Field(50, ge=1, description="Failed reads in a row before the source is reopened")

    def sources(self) -> list[str | int]:
        """Sources in priority order: stream URL first, then webcams."""
        sources: list[str | int] = [self.stream_url] if self.stream_url else []
        return sources + list(self.webcam_indices)


class VisionSettings(BaseModel):
    model_path: str = Field("yolov8n.pt", description="YOLO weights file (downloaded if missing)")
    person_confidence_min: float = Field(0.5, ge=0, le=1, description="Minimum YOLO confidence for a person")
    nms_iou_threshold: float = Field(0.7, ge=0, le=1, description="YOLO duplicate-box suppression overlap")
    track_iou_threshold: float = Field(
        0.7, ge=0, le=1, description="Tracker: same person if box overlap is above this"
    )
    pose_model_complexity: int = Field(
        1, ge=0, le=2, description="MediaPipe Pose model: 0 fast .. 2 accurate"
    )
    pose_min_detection_confidence: float = Field(
        0.5, ge=0, le=1, description="MediaPipe detection confidence"
    )
    pose_min_tracking_confidence: float = Field(0.5, ge=0, le=1, description="MediaPipe tracking confidence")


class FallSettings(BaseModel):
    """Mirrors FallThresholds; see fall/fall_detector.py for the algorithm."""

    tilt_threshold_deg: float = Field(
        60.0, gt=0, lt=180, description="Torso tilt from vertical that counts as not upright"
    )
    lying_margin_deg: float = Field(10.0, ge=0, description="Extra tilt on top of the threshold = lying")
    velocity_threshold_px: float = Field(0.5, ge=0, description="Torso movement per frame (pixels) = falling")
    falling_frames: int = Field(5, ge=1, description="Frames in a row tilted and moving to confirm a fall")
    lying_frames: int = Field(5, ge=1, description="Frames in a row lying to confirm a fall")
    min_visibility: float = Field(0.5, ge=0, le=1, description="Shoulders and hips must be this visible")

    def thresholds(self) -> FallThresholds:
        return FallThresholds(**self.model_dump())


class AlertSettings(BaseModel):
    cooldown_s: float = Field(60.0, ge=0, description="Minimum time between two alerts for the same person")
    forget_after_s: float = Field(
        30.0, gt=0, description="Forget people/devices not seen this long (never before cooldown ends)"
    )
    queue_size: int = Field(100, ge=1, description="Alerts waiting for delivery before new ones are dropped")
    workers: int = Field(2, ge=1, description="Alerts delivered at the same time")
    channel_timeout_s: float = Field(30.0, gt=0, description="Time limit for one attempt on one channel")
    retry_attempts: int = Field(3, ge=1, description="Attempts per channel before giving up")
    retry_base_delay_s: float = Field(
        1.0, ge=0, description="Wait after the first failure; doubles each time"
    )
    shutdown_drain_s: float = Field(15.0, ge=0, description="Time to finish queued alerts when stopping")

    def retry_policy(self) -> RetryPolicy:
        return RetryPolicy(attempts=self.retry_attempts, base_delay_s=self.retry_base_delay_s)


class DatabaseSettings(BaseModel):
    path: Path = Field(Path("fall_events.db"), description="SQLite file for fall events")


class LoggingSettings(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field("INFO", description="Log level")
    format: Literal["text", "json"] = Field("text", description="json for log collectors (Loki, ELK)")


class HealthSettings(BaseModel):
    enabled: bool = Field(True, description="Serve /health/live, /health/ready and /metrics")
    host: str = Field("127.0.0.1", description="Bind address; 0.0.0.0 inside Docker")
    port: int = Field(8080, ge=1, le=65535, description="HTTP port")


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
