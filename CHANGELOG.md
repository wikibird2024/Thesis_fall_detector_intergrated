# Changelog

Format: [Keep a Changelog](https://keepachangelog.com). Versions: [SemVer](https://semver.org).

## [Unreleased]

## [2.0.0] - 2026-09-28

Production-style rework of the thesis prototype. See `docs/ROADMAP.md` for the
phase-by-phase story.

### Fixed
- Camera fall detection: confidence was read from depth (z) instead of
  visibility, and an upright torso was measured as 180°.
- An MQTT outage no longer stops camera detection.
- A database error no longer prevents the alert from being sent.
- Sending an alert no longer freezes the video.
- ESP32-CAM stream reads a whole frame per call (was about 1 fps).
- Wearable alerts are processed even if the broker was slow at startup.
- Repeat alerts from one device after stale-state eviction.

### Changed
- **Settings use new names** (`MQTT__USERNAME`, `TELEGRAM__BOT_TOKEN`, ...);
  old names still work with a warning. See `.env.example`.
- A wearable message with bad or missing GPS, or without a timestamp, is now
  alerted with "location unknown" instead of being dropped.
- The same alert text on every channel, with time, map link and event id.
- The video window is optional (`CAMERA__SHOW_WINDOW`).
- Install with `pip install -e ".[vision]"`; `requirements.txt` is replaced by
  `pyproject.toml` and `requirements.lock.txt`.

### Added
- Automatic restart of crashed background tasks; MQTT reconnects forever.
- Alert queue with parallel delivery, per-channel timeout and retries.
- Event status in the database (`alerted` / `alert_failed`) and event ids.
- `/health/live`, `/health/ready`, `/metrics` (Prometheus); JSON logs.
- Command line: `run`, `check-config`, `events`, `config-docs`.
- Graceful shutdown on SIGTERM that delivers queued alerts first.
- Docker image, docker-compose, GitHub Actions CI, pre-commit hooks.
- 140+ automated tests.

### Removed
- pandas dependency.
- The `TORSO_ANGLE_THRESHOLD_HORIZONTAL` setting (it had no separate meaning).

## [1.0.0] - 2025

Thesis prototype.
