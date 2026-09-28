# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Environment (Python 3.10)
python3.10 -m venv .intergrate_venv && source .intergrate_venv/bin/activate
pip install -e ".[vision,dev]"        # CI installs only ".[dev]" (no torch)

make check                            # ruff + mypy + pytest: what CI runs
pytest -m "not vision"                # fast tests (no ML models)
pytest tests/unit/test_fall_detector.py -v
make format                           # ruff fix + format

fall-detector                         # run (also: python -m fall_detector, python main.py)
fall-detector check-config            # validate settings, secrets hidden
fall-detector events -n 20            # recent fall events
fall-detector config-docs > docs/CONFIGURATION.md   # after changing settings.py
```

## Configuration

Settings live in `src/fall_detector/settings.py` (pydantic-settings), read from env / `.env`
with nested names: `MQTT__USERNAME`, `TELEGRAM__BOT_TOKEN`, `AMI__SECRET`, `CAMERA__STREAM_URL`...
Template: `.env.example`. Reference: `docs/CONFIGURATION.md` (generated; a test fails if stale).
Version 1 flat names (`MQTT_USERNAME`...) are still mapped with a warning.
Telegram chat id: `python scripts/get_telegram_chat_id.py`.

## Architecture

Package `src/fall_detector/`. Details: `docs/ARCHITECTURE.md`; decisions: `docs/adr/`.

```
inputs/ (CameraPipeline via FrameAnalyzer, MQTTClient) -> processing/DetectionProcessor
  -> alerts/AlertDispatcher (queue) -> TelegramBot, AMITrigger + storage/FallEventRepository
```

- `app.py` is the composition root: builds everything from `Settings`, runs long-lived tasks
  under `runtime/supervisor.py` (restart with backoff), stops in order: inputs -> drain alerts -> rest.
- `DetectionProcessor` is synchronous and I/O-free: per-entity `FallDetector`, cooldown
  (monotonic clock, injectable), MQTT dedup by recent timestamps, stale eviction
  (never shorter than cooldown). Entity ids: `camera_person_<id>` or the wearable `device_id`.
- `AlertDispatcher.submit()` never blocks; workers save to DB and send on all channels in
  parallel with timeout + `runtime/retry.py`; status becomes `alerted` / `alert_failed`.
  A DB failure must never stop an alert.
- Channels implement `alerts/base.py:AlertChannel` (start / send / close). Send raises on failure.
- `fall/fall_detector.py`: pure logic, `FallThresholds` dataclass. Landmarks are
  `[x, y, z, visibility]`; visibility is index 3 (z is depth). Tilt is measured from straight up.
- Vision models (ultralytics, mediapipe) are imported lazily inside constructors so tests and
  CI run without them.
- MQTT payloads are validated by `DeviceFallMessage` (pydantic); bad GPS becomes "unknown",
  the alert is kept.
- Observability: `observability/metrics.py` (Prometheus), `health.py` (`/health/live`,
  `/health/ready`, `/metrics`), `logging_setup.py` (text or JSON). Use `logging.getLogger(__name__)`.
- SQLite schema changes: append to `MIGRATIONS` in `storage/repository.py`; never edit a shipped one.

## Tests

`tests/unit/` (fakes from `tests/fakes.py`, data from `tests/builders.py`), `tests/integration/`
(whole app, fakes at edges), `tests/vision/` (real models, marker `vision`). `asyncio_mode=auto`.
Never call real Telegram / Asterisk / brokers from tests; manual scripts are in `scripts/manual/`.
