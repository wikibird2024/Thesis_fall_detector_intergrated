# Contributing

## Workflow

```
main ──●────────────────●──────────     protected: only merged pull requests
        \              /
         ●──●──●──●───●                 feature/<short-name>, fix/<short-name>
         one topic per branch, small commits
```

1. `git switch -c fix/mqtt-timestamp` from an up-to-date `main`.
2. Make the change **with its test**. For a bug: write the failing test first.
3. `make check` (the same checks CI runs). Hooks from `pre-commit install`
   run ruff on every commit.
4. Push, open a pull request, fill in the checklist below, wait for green CI.
5. Squash-merge or rebase-merge; delete the branch.

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org):
`type(scope): what changed`, where type is `feat`, `fix`, `refactor`, `test`,
`docs`, `chore`, `ci` or `perf`.

```
fix(mqtt): keep alerts when GPS is invalid

A wearable with no GPS fix sent latitude "nan"; the whole message was
dropped. Now the location becomes "unknown" and the alert still goes out.
```

The body says *why*. The diff already shows *what*.

## Pull request checklist

- [ ] `make check` passes
- [ ] Tests added or changed; a bug fix has a regression test
- [ ] Settings changed → `fall-detector config-docs > docs/CONFIGURATION.md`
- [ ] Behavior users notice → `CHANGELOG.md` (Unreleased)
- [ ] Significant design choice → new ADR in `docs/adr/`
- [ ] Not checked on hardware? Say so in the PR description

## Code style

- Formatting and import order: ruff decides; don't argue with the formatter.
- Types on every function in `src/`; `mypy` must pass.
- Names: plain words, units in the name (`timeout_s`, `speed_px`), booleans
  as questions (`is_connected`, `has_gps_fix`).
- Logging: `logger = logging.getLogger(__name__)`, never `print`; `%s`
  arguments, not f-strings (formatting is skipped when the level is off).
- No I/O in `domain.py`, `fall/` or `processing/detection_processor.py`.
- New external service = new class behind a protocol, created in `app.py`.

## Tests

| Folder | What | Speed |
|---|---|---|
| `tests/unit/` | One module, fakes for everything around it | milliseconds |
| `tests/integration/` | The full app, fakes only at the edges | < 1 s |
| `tests/vision/` | Real YOLO / MediaPipe (`-m vision`) | seconds, needs `[vision]` |

Shared helpers: `tests/builders.py` (landmarks, boxes) and `tests/fakes.py`
(clock, channels, camera, analyzer). Never call real Telegram, Asterisk or a
broker from automated tests; use `scripts/manual/` for that.
