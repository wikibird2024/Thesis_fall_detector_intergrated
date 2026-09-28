"""Settings: typed values, nested env names, required secrets, legacy names."""

import os

import pytest
from pydantic import ValidationError

from fall_detector.settings import LEGACY_ENV_NAMES, Settings, load_settings

ALL_OFF = {"MQTT__ENABLED": "false", "TELEGRAM__ENABLED": "false", "AMI__ENABLED": "false"}


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch, tmp_path):
    """Tests must not see the developer's real .env or shell variables."""
    monkeypatch.chdir(tmp_path)
    names = list(LEGACY_ENV_NAMES) + list(LEGACY_ENV_NAMES.values())
    for name in names:
        monkeypatch.delenv(name, raising=False)
    yield
    for name in names:  # load_settings() writes os.environ directly; undo it
        os.environ.pop(name, None)


def set_env(monkeypatch, values):
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_defaults_match_version_1_values(monkeypatch):
    set_env(monkeypatch, ALL_OFF)
    settings = Settings()
    assert settings.alerts.cooldown_s == 60
    assert settings.camera.sources() == [2, 0, 1]
    assert settings.fall.thresholds().tilt_threshold_deg == 60
    assert settings.ami.extensions == ["6001", "6002", "6004"]


def test_nested_env_names_and_types(monkeypatch):
    set_env(
        monkeypatch,
        {
            **ALL_OFF,
            "ALERTS__COOLDOWN_S": "120",
            "CAMERA__WEBCAM_INDICES": "[0]",
            "CAMERA__STREAM_URL": "http://cam.local/stream",
        },
    )
    settings = Settings()
    assert settings.alerts.cooldown_s == 120.0
    assert settings.camera.sources() == ["http://cam.local/stream", 0]


def test_enabled_feature_without_secrets_fails_with_clear_names(monkeypatch):
    set_env(monkeypatch, {**ALL_OFF, "TELEGRAM__ENABLED": "true"})
    with pytest.raises(ValidationError) as error:
        Settings()
    assert "TELEGRAM__BOT_TOKEN" in str(error.value)
    assert "TELEGRAM__CHAT_ID" in str(error.value)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ALERTS__COOLDOWN_S", "-1"),
        ("MQTT__PORT", "70000"),
        ("FALL__MIN_VISIBILITY", "1.5"),
        ("LOGGING__LEVEL", "LOUD"),
    ],
)
def test_out_of_range_values_are_rejected(monkeypatch, name, value):
    set_env(monkeypatch, {**ALL_OFF, name: value})
    with pytest.raises(ValidationError):
        Settings()


def test_secrets_are_hidden_when_printed(monkeypatch):
    set_env(
        monkeypatch,
        {
            "MQTT__ENABLED": "false",
            "AMI__ENABLED": "false",
            "TELEGRAM__BOT_TOKEN": "123:SECRET",
            "TELEGRAM__CHAT_ID": "42",
        },
    )
    settings = Settings()
    assert "SECRET" not in str(settings.model_dump(mode="json"))
    assert settings.telegram.bot_token.get_secret_value() == "123:SECRET"


def test_legacy_names_in_env_file_still_work(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TELEGRAM_BOT_TOKEN=old-token\nTELEGRAM_CHAT_ID=7\nMQTT__ENABLED=false\nAMI__ENABLED=false\n"
    )
    settings = load_settings(env_file)
    assert settings.telegram.bot_token.get_secret_value() == "old-token"
    assert settings.telegram.chat_id == "7"


def test_new_name_wins_over_legacy_name(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TELEGRAM_CHAT_ID=old\nTELEGRAM__CHAT_ID=new\nTELEGRAM__BOT_TOKEN=t\n"
        "MQTT__ENABLED=false\nAMI__ENABLED=false\n"
    )
    assert load_settings(env_file).telegram.chat_id == "new"
