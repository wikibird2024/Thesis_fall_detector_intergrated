"""Command line and logging setup."""

import json
import logging

import pytest

from fall_detector.__main__ import EXIT_BAD_CONFIG, EXIT_OK, main
from fall_detector.observability.logging_setup import JsonFormatter, configure_logging
from fall_detector.settings import LEGACY_ENV_NAMES

ALL_OFF = "MQTT__ENABLED=false\nTELEGRAM__ENABLED=false\nAMI__ENABLED=false\n"


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for name in list(LEGACY_ENV_NAMES) + list(LEGACY_ENV_NAMES.values()):
        monkeypatch.delenv(name, raising=False)
    yield
    configure_logging()  # undo JSON/level changes for later tests


def write_env(tmp_path, text: str):
    path = tmp_path / ".env"
    path.write_text(text)
    return str(path)


def test_check_config_prints_settings_without_secrets(tmp_path, capsys):
    env = write_env(
        tmp_path,
        "MQTT__ENABLED=false\nAMI__ENABLED=false\nTELEGRAM__BOT_TOKEN=123:TOPSECRET\nTELEGRAM__CHAT_ID=1\n",
    )
    assert main(["--env-file", env, "check-config"]) == EXIT_OK
    out = capsys.readouterr().out
    assert json.loads(out)["telegram"]["chat_id"] == "1"
    assert "TOPSECRET" not in out


def test_invalid_config_exits_2_without_leaking_values(tmp_path, capsys):
    env = write_env(tmp_path, ALL_OFF + "MQTT__PASSWORD=hunter2\nALERTS__COOLDOWN_S=-1\n")
    assert main(["--env-file", env, "check-config"]) == EXIT_BAD_CONFIG
    captured = capsys.readouterr()
    assert "ALERTS__COOLDOWN_S" in captured.out + captured.err
    assert "hunter2" not in captured.out + captured.err


def test_events_command_lists_database_rows(tmp_path, capsys):
    env = write_env(tmp_path, ALL_OFF + f"DATABASE__PATH={tmp_path / 'e.db'}\n")
    assert main(["--env-file", env, "events"]) == EXIT_OK
    assert "No fall events" in capsys.readouterr().out


def test_json_log_line_is_parseable():
    record = logging.LogRecord("fall_detector.x", logging.WARNING, __file__, 1, "fall %s", ("ok",), None)
    entry = json.loads(JsonFormatter().format(record))
    assert (
        entry["level"] == "WARNING" and entry["message"] == "fall ok" and entry["logger"] == "fall_detector.x"
    )


def test_configure_logging_quiets_noisy_libraries():
    configure_logging("DEBUG")
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger().level == logging.DEBUG


def test_configuration_doc_is_up_to_date():
    """Fails when settings.py changed but docs/CONFIGURATION.md was not regenerated."""
    from pathlib import Path

    from fall_detector.config_docs import render_configuration_markdown

    doc = Path(__file__).resolve().parents[2] / "docs" / "CONFIGURATION.md"
    assert doc.read_text() == render_configuration_markdown(), (
        "run: fall-detector config-docs > docs/CONFIGURATION.md"
    )
