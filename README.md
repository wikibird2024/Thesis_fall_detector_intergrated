# Fall Detector

Real-time fall detection for elderly care. It watches a camera (YOLOv8 +
MediaPipe Pose) and listens to wearable sensors (ESP32 over MQTT). When someone
falls it alerts caregivers on Telegram (with a photo) and rings their SIP
phones through Asterisk. Every event is stored in SQLite.

```
 Camera / ESP32-CAM ──> YOLO ──> tracker ──> pose ──┐
                                                    ├──> fall decision ──> alert queue ──┬──> Telegram
 Wearable (ESP32) ──MQTT──> validated message ──────┘   (cooldown, dedup)                ├──> Asterisk call + SIP msg
                                                                                          └──> SQLite (status)
```

Built to run unattended: every part restarts itself after a crash, lost
cameras and brokers reconnect, a slow alert channel never blocks detection,
and `/health/ready` tells you when something is wrong.

## Quick start

```bash
# 1. Python 3.10 environment
python3.10 -m venv .intergrate_venv && source .intergrate_venv/bin/activate

# 2. Install app + vision models + dev tools, and the git hooks
make install-dev                      # or: pip install -e ".[vision,dev]" && pre-commit install

# 3. Settings
cp .env.example .env                  # fill in MQTT / Telegram / Asterisk credentials
fall-detector check-config            # validates, prints values (secrets hidden)

# 4. Run
fall-detector                         # or: python -m fall_detector, or: python main.py
```

Press `q` in the video window, Ctrl+C, or send SIGTERM to stop. Queued alerts
are delivered before the process exits.

Don't need a feature? Turn it off instead of leaving credentials empty:
`MQTT__ENABLED=false`, `TELEGRAM__ENABLED=false`, `AMI__ENABLED=false`,
`CAMERA__ENABLED=false`.

## Commands

| Command | What it does |
|---|---|
| `fall-detector` / `fall-detector run` | Run the system |
| `fall-detector check-config` | Validate settings and print them |
| `fall-detector events -n 20` | Show the latest fall events from the database |
| `fall-detector config-docs` | Regenerate `docs/CONFIGURATION.md` |
| `make check` | Lint + type check + tests (what CI runs) |
| `make test` / `make cov` | Tests / tests with coverage |
| `make format` | Auto-fix style |

## Operations

| Endpoint | Use |
|---|---|
| `http://127.0.0.1:8080/health/live` | Process is up (Docker healthcheck) |
| `http://127.0.0.1:8080/health/ready` | 200 when camera, MQTT and alerts all work; 503 + JSON reason otherwise |
| `http://127.0.0.1:8080/metrics` | Prometheus metrics: frames, falls, alert deliveries, reconnects |

Docker: `docker compose up -d` (details and troubleshooting in
[docs/RUNBOOK.md](docs/RUNBOOK.md)).

## Project layout

```
src/fall_detector/
  __main__.py       command line
  app.py            builds and wires all parts; start/stop order
  settings.py       typed, validated configuration
  domain.py         FallEvent, Alert: shared data types
  inputs/           MQTT client, video sources (webcam, ESP32 stream)
  vision/           YOLO detector, IoU tracker, MediaPipe pose, drawing
  fall/             the fall decision (pure logic)
  processing/       camera pipeline, detection processor (cooldown, dedup)
  alerts/           Telegram, Asterisk, dispatcher (queue, retries, timeouts)
  storage/          SQLite repository with schema migrations
  runtime/          retry policy, task supervisor
  observability/    logging, metrics, health server
tests/
  unit/             one file per module, fakes instead of network/camera
  integration/      the whole app with fakes only at the edges
  vision/           real-model smoke tests (marked `vision`)
docs/               architecture, configuration, runbook, roadmap, decisions (ADRs)
scripts/            chat-id helper; manual Asterisk/MQTT checks
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md): how the parts fit and why
- [Configuration](docs/CONFIGURATION.md): every setting (generated)
- [Runbook](docs/RUNBOOK.md): deploy, monitor, troubleshoot
- [Roadmap](docs/ROADMAP.md): what changed in each phase and what to learn from it
- [Decisions](docs/adr/): architecture decision records
- [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md)
