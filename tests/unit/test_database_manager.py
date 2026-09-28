"""database_manager: stores fall events in SQLite."""

import pytest

from fall_detector.storage import database_manager as db


@pytest.fixture(autouse=True)
def temp_database(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_FILE", str(tmp_path / "test.db"))
    db.create_table()


def event(**overrides):
    data = {"timestamp": 1_700_000_000, "device_id": "d1", "fall_detected": True,
            "latitude": 1.0, "longitude": 2.0, "has_gps_fix": True}
    data.update(overrides)
    return data


def test_insert_returns_increasing_ids():
    assert db.insert_fall_event(event()) == 1
    assert db.insert_fall_event(event()) == 2


def test_new_event_is_pending_and_status_can_change():
    event_id = db.insert_fall_event(event())
    db.update_alert_status(event_id, "resolved")

    rows = db.get_all_alerts()
    assert rows.loc[0, "status"] == "resolved"
