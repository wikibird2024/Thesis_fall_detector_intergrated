# Runbook

How to deploy, watch and fix the fall detector. Written for the person on call.

## Deploy

### Docker (recommended for a server)

```bash
cp .env.example .env              # fill in credentials
docker compose up -d --build
docker compose logs -f fall-detector
curl -s localhost:8080/health/ready | python -m json.tool
```

- Data (SQLite) lives in the `fall-data` volume and survives rebuilds.
- Asterisk on the same host: set `AMI__HOST=host.docker.internal`.
- USB webcam: uncomment `devices:` in `docker-compose.yml`.
- `docker compose stop` sends SIGTERM; the app delivers queued alerts first
  (up to `ALERTS__SHUTDOWN_DRAIN_S`, compose waits 30 s).

### Bare metal / laptop

```bash
make install            # once
fall-detector           # CAMERA__SHOW_WINDOW=false on a headless machine
```

For a service that starts on boot, use a systemd unit with `Restart=always`
and `KillSignal=SIGTERM`.

## Watch

| Check | Healthy | Look at |
|---|---|---|
| `GET /health/live` | 200 | Process is up |
| `GET /health/ready` | 200 | JSON shows which part is not ready |
| Log line `Heartbeat: ready=True` | every 60 s | Missing = event loop blocked |
| `fall_detector_frames_processed_total` | rising | Flat = camera stuck |
| `fall_detector_alerts_sent_total{outcome="failed"}` | not rising | A channel is down |
| `fall_detector_task_restarts_total` | not rising | Something crashes in a loop |
| `fall_detector_alerts_dropped_total` | 0 | Queue full: channels far too slow |

Suggested Prometheus alerts:

```yaml
- alert: FallDetectorNotReady
  expr: up{job="fall-detector"} == 0 or fall_detector_camera_connected == 0
  for: 2m
- alert: FallDetectorAlertDeliveryFailing
  expr: increase(fall_detector_alerts_sent_total{outcome="failed"}[15m]) > 0
- alert: FallDetectorNoFrames
  expr: rate(fall_detector_frames_processed_total[5m]) == 0
  for: 5m
```

Follow one fall: every alert has an event id (`Event: 3f9c1a2b7d4e`). Search the
logs for it, and find the row with `fall-detector events`.

## Troubleshoot

| Symptom | Likely cause | Fix |
|---|---|---|
| Exits at start, "Invalid configuration" | Missing or wrong setting | Read the list it prints; `fall-detector check-config` |
| `ready: false`, camera `connected: false` | No camera at the configured sources | Check `CAMERA__STREAM_URL`, `CAMERA__WEBCAM_INDICES`; `ls /dev/video*` |
| `No working video source` every few seconds | Same as above | Same as above |
| mqtt `connected: false` | Broker unreachable or wrong credentials | Check `MQTT__HOST`, key; log shows the MQTT error |
| `MQTT message rejected` | Wearable sends a different JSON format | Compare the logged payload with `DeviceFallMessage` in `inputs/mqtt_client.py` |
| Telegram alert "failed after retries" | Token revoked, bot removed from chat, or network | Log shows the Telegram error; test with `scripts/get_telegram_chat_id.py` |
| `Asterisk reached only [...]` | Some phones offline / not registered | `asterisk -rx "pjsip show endpoints"` |
| `no extension reached` | AMI user lacks `originate` permission or dialplan missing | Check `manager.conf` and extension `9999` in context `internal` |
| `Could not save event` | Disk full or DB file not writable | `df -h`; file owner. Alerts still go out. |
| Too many false alarms | Threshold too sensitive for this camera | Raise `FALL__LYING_FRAMES` / `FALL__FALLING_FRAMES`; see `docs/ARCHITECTURE.md` §6 |
| `Task X crashed` repeating | Bug or broken dependency | Stack trace is in the log right above; open an issue with it |
| Deprecated setting names warning | `.env` from version 1 | Rename per `.env.example` (old names still work) |

## Backup and data

```bash
# consistent copy while running (SQLite online backup)
sqlite3 fall_events.db ".backup 'backup-$(date +%F).db'"
```

Schema upgrades run automatically at start (`PRAGMA user_version` tracks them).
Back up before upgrading to a new version.
