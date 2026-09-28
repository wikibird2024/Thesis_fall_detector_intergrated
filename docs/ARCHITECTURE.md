# Architecture

## 1. The big picture

```
                           ┌────────────────────── app.py (composition root) ───────────────────────┐
                           │  builds every part from Settings, starts them under a TaskSupervisor   │
                           └────────────────────────────────────────────────────────────────────────┘

 INPUTS                          DECISION                          DELIVERY
 ──────                          ────────                          ────────
 CameraPipeline ─┐               DetectionProcessor                AlertDispatcher
  read (thread)  │  per person   ├ FallDetector per entity         ├ queue (never blocks callers)
  analyze(thread)├──────────────>├ cooldown per entity   ─submit─> ├ workers: save + send in parallel
                 │               ├ dedup per device               ├ retry + timeout per channel
 MQTTClient ─────┘  validated    └ evict stale state              ├──> TelegramBot   (photo / text)
  reconnect forever  message                                      ├──> AMITrigger    (call + SIP msg)
                                                                   └──> FallEventRepository (SQLite)

 SUPPORT: runtime/ (retry, supervisor) · observability/ (logs, metrics, /health) · settings.py
```

Dependencies point one way: `inputs → processing → alerts → storage`, and all of
them may use `domain.py`. Nothing imports `app.py` except the command line.

## 2. Layers and their rules

| Layer | Modules | Rule |
|---|---|---|
| Domain | `domain.py`, `fall/` | Pure data and logic. No I/O, no settings, no frameworks. Easiest code to test. |
| Inputs | `inputs/` | Turn the outside world into domain types. Validate at the edge (`DeviceFallMessage`). |
| Vision | `vision/` | Heavy models behind the `FrameAnalyzer` protocol; imported lazily. |
| Processing | `processing/` | Decide. `DetectionProcessor` is synchronous and does no I/O. |
| Alerts | `alerts/` | Deliver. Channels only know "send once"; the dispatcher owns retry/timeout. |
| Storage | `storage/` | Only place with SQL. Repository pattern + numbered migrations. |
| Runtime | `runtime/`, `observability/` | Cross-cutting: keep tasks alive, measure, report health. |
| Composition | `app.py`, `__main__.py` | The only code that knows concrete classes. |

## 3. One fall, end to end

```
t=0     frame N: FallDetector confirms fall for camera_person_3
        DetectionProcessor: cooldown ok -> FallEvent(event_id=3f9c1a2b7d4e) + JPEG snapshot
        dispatcher.submit()  -> returns at once; camera continues with frame N+1
        log: WARNING FALL ALERT [3f9c1a2b7d4e] ...
t+1ms   worker picks the alert:
          ├─ repository.save()          (thread)      -> row status "pending"
          ├─ Telegram send_photo        (retry x3, 30 s timeout each)
          └─ Asterisk call + SIP msg    (retry x3, 30 s timeout each)
t+~2s   any channel ok -> status "alerted"   (all failed -> "alert_failed")
```

The same `event_id` appears in the log, the Telegram text, the SIP message and
the database row. That is a *correlation id*: search for it to follow one fall
through every system.

## 4. Failure behavior

| What fails | What happens | Where |
|---|---|---|
| Camera unplugged / stream drops | Source released, reopened every `CAMERA__RECONNECT_DELAY_S`; `/health/ready` = 503 | `camera_pipeline.py` |
| MQTT broker down | Reconnect with backoff 1 s → 60 s, forever; camera unaffected | `mqtt_client.py` |
| Any background task crashes | Logged with stack trace, restarted with backoff, `task_restarts_total` +1 | `supervisor.py` |
| Telegram slow / down | Retried with backoff (honors flood-control wait); other channels unaffected | `dispatcher.py` |
| Photo upload fails | Falls back to text | `telegram_bot.py` |
| Asterisk unreachable | panoramisk reconnects every 2 s by itself; an alert in the gap fails fast and the dispatcher retries it | `ami_trigger.py` |
| Database locked / disk full | Alert still sent; error logged; `db_writes_total{outcome="failed"}` | `dispatcher.py` |
| Alert queue full (100) | Alert dropped, logged at ERROR, `alerts_dropped_total` +1 | `dispatcher.py` |
| Bad MQTT payload | Rejected and logged; bad GPS only → alert with "location unknown" | `mqtt_client.py` |
| Bad configuration | Refuses to start, lists every problem, exit code 2 | `settings.py` |
| SIGTERM / Ctrl+C | Stop inputs → deliver queued alerts (≤ 15 s) → close | `app.py` |

## 5. Concurrency model

One asyncio event loop runs everything that waits on the network. Work that
blocks (camera read, YOLO, MediaPipe, SQLite) runs in worker threads with
`asyncio.to_thread`, so a 100 ms YOLO call never delays an MQTT message or an
alert. There is no shared mutable state between threads: the analyzer works on
its own frame, and the repository opens a fresh connection per call.

## 6. The fall algorithm

`fall/fall_detector.py`, one instance per tracked person:

```
tilt = angle between hip→shoulder line and straight up   (0° standing, 90° lying, 180° upside down)
speed = torso center movement since last frame (pixels)

falling frame : tilt > 60°       and speed > 0.5 px
lying frame   : tilt > 60° + 10°
fall confirmed: 5 falling frames in a row, or 5 lying frames in a row
```

Known limits, candidates for the next phase:
- The speed threshold is in pixels, so it depends on distance to the camera.
  Normalizing by torso length would make it scale-free.
- A falling frame resets the lying count and the other way round, so jitter
  around 0.5 px can delay a confirmation. Counting "down" frames of either kind
  together is a simple improvement; it needs recorded videos to tune.
- A single 2D angle can't see falls straight toward or away from the camera.

## 7. Decisions

Each important choice has a short record in [adr/](adr/): what was decided,
why, and what it costs.
