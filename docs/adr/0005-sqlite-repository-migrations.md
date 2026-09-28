# 0005. SQLite behind a repository, numbered migrations

- Status: Accepted
- Date: 2026-09-28

## Context
Database code was free functions using pandas for single-row inserts. There
was no way to change the schema of an existing `fall_events.db`.

## Decision
`FallEventRepository` is the only code that writes SQL. The schema is a list of
numbered migrations; `PRAGMA user_version` records how many have run, and
`migrate()` runs the rest at startup. Version 1 databases are upgraded in
place. WAL mode lets readers work while the app writes. pandas is gone.

## Consequences
- Schema changes are reviewed code, applied the same way everywhere.
- Moving to PostgreSQL later changes one file (plus a migration tool such as
  Alembic).
- Migrations must never be edited after release; mistakes are fixed with a
  new migration.
