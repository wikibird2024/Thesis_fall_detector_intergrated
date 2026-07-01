# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Create and activate virtualenv (Python 3.10)
python3.10 -m venv .intergrate_venv
source .intergrate_venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the system
python main.py

# Run tests
pytest tests/

# Run a single test file
pytest tests/test_fall.py -v
```

## Environment Setup

To find your Telegram `CHAT_ID`, run `python get_telegram_id_bot.py`, then message your bot.

Create a `.env` file in the project root with the following secrets before running:

```
MQTT_USERNAME=...
MQTT_PASSWORD=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
AMI_USERNAME=...
AMI_SECRET=...
VIDEO_STREAM_URL=http://...  # Optional: ESP32-CAM MJPEG stream URL
```

All sensitive credentials are loaded via `python-dotenv` in `config/config.py`. Non-secret tunable parameters (detection thresholds, feature flags) are set directly in that file.

## Architecture

The system is a fully asynchronous (`asyncio`) fall detection pipeline with two parallel input sources and three alert channels.

### Async Task Structure (`main.py`)

`asyncio.run(main())` starts concurrent tasks via `asyncio.wait(tasks, return_when=FIRST_COMPLETED)`:
- **`camera_processing_loop`** — reads frames, runs detection pipeline, feeds `DetectionProcessor`
- **`mqtt_listener`** (if `ENABLE_MQTT`) — `MQTTClient.run_forever()` connects to Adafruit IO and fills an internal queue
- **`mqtt_processor_loop`** — drains the MQTT queue and feeds `DetectionProcessor`
- **`heartbeat_loop`** — periodic INFO log to confirm liveness

### Camera Detection Pipeline

```
VideoCapture / ESP32StreamWrapper
  → HumanDetector.detect_humans()        # YOLOv8n: returns [x1,y1,x2,y2,conf,cls]
  → PersonTracker.update()               # IoU-based tracker: assigns stable person_id
  → SkeletonTracker.track_from_box()     # MediaPipe Pose: returns 33 landmarks [x,y,z,vis]
  → DetectionProcessor.handle_camera_data()
```

`utils/video_utils.py` (`find_and_connect_source`) tries sources in priority order: `VIDEO_STREAM_URL` → webcam index 2 → 0 → 1. HTTP URLs use `ESP32StreamWrapper` (MJPEG with auto-reconnect); integers use `cv2.VideoCapture`.

### MQTT Input Path

`MQTTClient` (`comm/mqtt_client.py`) uses `aiomqtt` and normalizes incoming JSON payloads to a standard dict with `device_id`, `fall_detected`, `latitude`, `longitude`, `has_gps_fix`, and `timestamp`. Messages are enqueued; `DetectionProcessor.handle_mqtt_data()` processes them from the queue.

### Fall Detection Logic (`fall/fall_detector.py`)

Each tracked entity gets its own stateful `FallDetector` instance. A fall is confirmed when either:
- **Active fall**: torso angle > threshold AND torso velocity > threshold for `FALL_DURATION_THRESHOLD` consecutive frames
- **Lying state**: torso angle significantly exceeded for `FALL_STATE_DURATION_THRESHOLD` consecutive frames

Landmarks must have confidence ≥ `MIN_LANDMARK_CONFIDENCE` on the 4 key points (shoulders + hips); otherwise state resets.

### Alert Pipeline (`processing/detection_processor.py`)

`DetectionProcessor` is the central hub:
- Maintains a `FallDetector` per `entity_id` (camera: `camera_person_<id>`, MQTT: `device_id`)
- **Cooldown**: 1-minute per entity between alerts (`last_alert_timestamps`)
- **Deduplication** (MQTT only): drops events with duplicate `timestamp` field (`last_fall_timestamps`)
- On confirmed fall: inserts to SQLite DB (`database_manager.insert_fall_event`), then fires AMI and Telegram alerts **in parallel** via `asyncio.gather`

### Alert Channels

| Channel | Class | Protocol |
|---|---|---|
| Phone call + SIP message | `AMITrigger` (`comm/ami_trigger.py`) | Asterisk AMI via `panoramisk`; calls extension 9999, sends `MessageSend` to `EXTENSIONS` list |
| Telegram | `TelegramBot` (`comm/telegram_bot.py`) | `python-telegram-bot`; sends photo+caption if frame available, falls back to text |
| Database | `database_manager.py` | SQLite (`fall_events.db`); blocking calls wrapped in `asyncio.to_thread` |

### Configuration (`config/config.py`)

All tunables live here. Toggle features with `ENABLE_MQTT`, `ENABLE_AMI`, `ENABLE_TELEGRAM`. The `get_video_sources()` function controls source priority order.
