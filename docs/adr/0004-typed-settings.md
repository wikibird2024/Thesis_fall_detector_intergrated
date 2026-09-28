# 0004. Typed settings with pydantic-settings

- Status: Accepted
- Date: 2026-09-28

## Context
Settings were module constants in `config.py`, some from `.env`. Typos and
wrong types showed up only when the code path ran, possibly days later.

## Decision
One `Settings` model (pydantic-settings) with nested groups, read from the
environment and `.env` with `GROUP__NAME` variables. Every field has a type,
a range and a description. Secrets are `SecretStr` (hidden when printed).
Missing credentials for an enabled feature stop the start with a list of
every problem. Version 1 names are still read, with a deprecation warning.
`docs/CONFIGURATION.md` is generated from the model, and a test checks it is
up to date.

## Consequences
- Wrong configuration fails in the first second, with a clear message.
- Same mechanism for laptop (`.env`), Docker (`env_file`) and CI (env vars).
- Settings are passed to constructors (dependency injection); no module reads
  global config, which keeps tests independent.
