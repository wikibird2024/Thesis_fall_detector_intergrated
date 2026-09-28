"""Fall event storage (SQLite).

Repository pattern: the rest of the app calls save / set_status / recent and
never writes SQL. Swapping SQLite for PostgreSQL later only touches this file.

Schema changes are numbered migrations. SQLite's `PRAGMA user_version` stores
which ones already ran, so an old database from version 1 is upgraded in place
on startup and a new one is built from scratch the same way.

The methods are blocking. Async code calls them with asyncio.to_thread().
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from fall_detector.domain import EventStatus, FallEvent

logger = logging.getLogger(__name__)

# Index i holds the SQL that upgrades the schema from version i to i + 1.
# Never edit a migration that has shipped; add a new one.
MIGRATIONS: list[str] = [
    # 0 -> 1: the original version 1 table.
    """
    CREATE TABLE IF NOT EXISTS fall_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        device_id TEXT,
        fall_detected INTEGER,
        latitude REAL,
        longitude REAL,
        has_gps_fix INTEGER,
        status TEXT NOT NULL
    );
    """,
    # 1 -> 2: correlation id and source, plus indexes for the common queries.
    """
    ALTER TABLE fall_events ADD COLUMN event_id TEXT;
    ALTER TABLE fall_events ADD COLUMN source TEXT;
    CREATE UNIQUE INDEX IF NOT EXISTS ux_fall_events_event_id ON fall_events(event_id);
    CREATE INDEX IF NOT EXISTS ix_fall_events_timestamp ON fall_events(timestamp);
    """,
]


@dataclass(frozen=True)
class StoredFallEvent:
    id: int
    event_id: str | None
    timestamp: str
    source: str | None
    entity_id: str | None
    latitude: float | None
    longitude: float | None
    has_gps_fix: bool
    status: str


class FallEventRepository:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # One short-lived connection per call: safe across threads, and
        # SQLite opens fast. timeout waits for a lock instead of failing at once.
        conn = sqlite3.connect(self.path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            with conn:  # commits on success, rolls back on error
                yield conn
        finally:
            conn.close()

    def schema_version(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("PRAGMA user_version").fetchone()[0])

    def migrate(self) -> int:
        """Bring the schema up to date. Safe to call on every start."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")  # readers don't block the writer
        current = self.schema_version()
        for version in range(current, len(MIGRATIONS)):
            with self._connect() as conn:
                conn.executescript(
                    f"BEGIN;\n{MIGRATIONS[version]}\nPRAGMA user_version = {version + 1};\nCOMMIT;"
                )
            logger.info("Database schema migrated to version %d", version + 1)
        return len(MIGRATIONS)

    def save(self, event: FallEvent) -> int:
        """Store a new event with status 'pending'. Returns the row id."""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO fall_events
                    (event_id, timestamp, source, device_id, fall_detected,
                     latitude, longitude, has_gps_fix, status)
                VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.occurred_at.isoformat(),
                    event.source.value,
                    event.entity_id,
                    event.latitude,
                    event.longitude,
                    int(event.has_gps_fix),
                    EventStatus.PENDING.value,
                ),
            )
            row_id = cursor.lastrowid
        assert row_id is not None
        return row_id

    def set_status(self, event_id: str, status: EventStatus | str) -> bool:
        """Returns False if no event has that id."""
        value = status.value if isinstance(status, EventStatus) else status
        with self._connect() as conn:
            cursor = conn.execute("UPDATE fall_events SET status = ? WHERE event_id = ?", (value, event_id))
            return cursor.rowcount > 0

    def recent(self, limit: int = 20) -> list[StoredFallEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, event_id, timestamp, source, device_id, latitude, longitude,
                       has_gps_fix, status
                FROM fall_events ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            StoredFallEvent(
                id=row["id"],
                event_id=row["event_id"],
                timestamp=row["timestamp"],
                source=row["source"],
                entity_id=row["device_id"],
                latitude=row["latitude"],
                longitude=row["longitude"],
                has_gps_fix=bool(row["has_gps_fix"]),
                status=row["status"],
            )
            for row in rows
        ]
