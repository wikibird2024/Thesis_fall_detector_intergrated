"""FallEventRepository: SQLite storage with in-place schema migrations."""

import sqlite3

import pytest

from fall_detector.domain import EventSource, EventStatus, FallEvent
from fall_detector.storage.repository import MIGRATIONS, FallEventRepository


@pytest.fixture
def repository(tmp_path):
    repo = FallEventRepository(tmp_path / "events.db")
    repo.migrate()
    return repo


def wearable_event(**overrides) -> FallEvent:
    values = dict(
        source=EventSource.WEARABLE, entity_id="wrist-01", latitude=10.7, longitude=106.6, has_gps_fix=True
    )
    values.update(overrides)
    return FallEvent(**values)


def test_new_database_is_at_latest_schema(repository):
    assert repository.schema_version() == len(MIGRATIONS)


def test_migrate_twice_is_harmless(repository):
    assert repository.migrate() == len(MIGRATIONS)


def test_save_then_read_back(repository):
    event = wearable_event()
    row_id = repository.save(event)

    [stored] = repository.recent()
    assert stored.id == row_id
    assert stored.event_id == event.event_id
    assert stored.source == "esp32"
    assert stored.entity_id == "wrist-01"
    assert stored.has_gps_fix is True
    assert stored.status == EventStatus.PENDING.value


def test_status_update_by_event_id(repository):
    event = wearable_event()
    repository.save(event)

    assert repository.set_status(event.event_id, EventStatus.ALERTED)
    assert repository.recent()[0].status == "alerted"
    assert not repository.set_status("no-such-id", EventStatus.ALERTED)


def test_recent_is_newest_first_and_limited(repository):
    for n in range(5):
        repository.save(wearable_event(entity_id=f"d{n}"))
    assert [e.entity_id for e in repository.recent(limit=2)] == ["d4", "d3"]


def test_same_event_cannot_be_saved_twice(repository):
    event = wearable_event()
    repository.save(event)
    with pytest.raises(sqlite3.IntegrityError):
        repository.save(event)


def test_version_1_database_is_upgraded_and_keeps_old_rows(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:  # database exactly as version 1 created it
        conn.executescript(MIGRATIONS[0])
        conn.execute(
            "INSERT INTO fall_events (timestamp, device_id, fall_detected, status) VALUES (?, ?, 1, ?)",
            ("2025-01-01T10:00:00", "camera_person_3", "pending"),
        )
    conn.close()

    repository = FallEventRepository(path)
    repository.migrate()

    [old_row] = repository.recent()
    assert old_row.entity_id == "camera_person_3"
    assert old_row.event_id is None
    repository.save(wearable_event())  # new columns work
