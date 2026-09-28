# Architecture decision records (ADRs)

One short file per important decision: the context, the choice, and what it
costs. Decisions are never edited after they are accepted; a later ADR can
replace an earlier one (status: "Superseded by 00NN").

| # | Decision | Status |
|---|---|---|
| [0001](0001-src-layout-and-pyproject.md) | `src/` layout and `pyproject.toml` | Accepted |
| [0002](0002-supervised-tasks.md) | Supervise each background task on its own | Accepted |
| [0003](0003-alert-dispatcher-queue.md) | Queue alerts; deliver and store in parallel | Accepted |
| [0004](0004-typed-settings.md) | Typed settings with pydantic-settings | Accepted |
| [0005](0005-sqlite-repository-migrations.md) | SQLite behind a repository, numbered migrations | Accepted |

New ADR: copy the newest file, take the next number, keep it under one page.
