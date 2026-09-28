# Configuration

> Generated from `src/fall_detector/settings.py`. Do not edit by hand:
> run `fall-detector config-docs > docs/CONFIGURATION.md`.

Settings are read from environment variables and from `.env` (see `.env.example`).
Groups use a double underscore: `GROUP__SETTING=value`. Lists are JSON, e.g.
`AMI__EXTENSIONS=["6001","6002"]`. Every value is checked at startup; run
`fall-detector check-config` to see the values in effect (secrets hidden).

Version 1 names (`MQTT_USERNAME`, `TELEGRAM_BOT_TOKEN`, ...) still work and log
a warning asking you to rename them.

## mqtt

Wearable (ESP32) fall messages from an MQTT broker.

| Variable | Type | Default | Allowed | Meaning |
|---|---|---|---|---|
| `MQTT__ENABLED` | bool | `True` |  | Listen for wearable fall messages |
| `MQTT__HOST` | str | `io.adafruit.com` |  | Broker host name |
| `MQTT__PORT` | int | `1883` | >= 1, <= 65535 | Broker port |
| `MQTT__TOPIC` | str | `tranhao/feeds/fall_alert` |  | Topic the wearable publishes to |
| `MQTT__USERNAME` | str (optional) | - |  | Broker user (required when enabled) |
| `MQTT__PASSWORD` | secret (optional) | - |  | Broker password or key (required when enabled) |
| `MQTT__QOS` | int | `0` | >= 0, <= 2 | Subscribe QoS; 1 = at least once, if the broker supports it |
| `MQTT__KEEPALIVE_S` | int | `60` | >= 5 | Ping interval that detects a dead connection |
| `MQTT__RECONNECT_MIN_S` | float | `1.0` | > 0 | First wait after a disconnect; doubles each try |
| `MQTT__RECONNECT_MAX_S` | float | `60.0` | > 0 | Longest wait between reconnect tries |
| `MQTT__QUEUE_SIZE` | int | `1000` | >= 1 | Messages buffered between network and processing |

## telegram

| Variable | Type | Default | Allowed | Meaning |
|---|---|---|---|---|
| `TELEGRAM__ENABLED` | bool | `True` |  | Send alerts to Telegram |
| `TELEGRAM__BOT_TOKEN` | secret (optional) | - |  | Token from @BotFather (required when enabled) |
| `TELEGRAM__CHAT_ID` | str (optional) | - |  | Chat to alert; see scripts/get_telegram_chat_id.py (required when enabled) |
| `TELEGRAM__SEND_STARTUP_MESSAGE` | bool | `True` |  | Send a message when the system starts |

## ami

Asterisk Manager Interface: phone call + SIP message to each extension.

| Variable | Type | Default | Allowed | Meaning |
|---|---|---|---|---|
| `AMI__ENABLED` | bool | `True` |  | Call and message SIP phones through Asterisk |
| `AMI__HOST` | str | `127.0.0.1` |  | Asterisk host |
| `AMI__PORT` | int | `5038` | >= 1, <= 65535 | AMI port |
| `AMI__USERNAME` | str (optional) | - |  | AMI user from manager.conf (required when enabled) |
| `AMI__SECRET` | secret (optional) | - |  | AMI secret (required when enabled) |
| `AMI__EXTENSIONS` | list[str] | `["6001", "6002", "6004"]` |  | SIP extensions to alert (JSON list) |
| `AMI__CALLER_ID` | str | `FallAlertSystem <1000>` |  | Caller id shown on the phones |
| `AMI__CONTEXT` | str | `internal` |  | Dialplan context for the call |
| `AMI__HANGUP_EXTENSION` | str | `9999` |  | Dialplan extension that plays the alert and hangs up |
| `AMI__CLEANUP_DELAY_S` | float | `3.0` | >= 0 | Pause after an alert so Asterisk can free channels |

## camera

| Variable | Type | Default | Allowed | Meaning |
|---|---|---|---|---|
| `CAMERA__ENABLED` | bool | `True` |  | Run camera-based detection (loads the vision models) |
| `CAMERA__STREAM_URL` | str (optional) | - |  | ESP32-CAM MJPEG stream URL, tried before webcams |
| `CAMERA__WEBCAM_INDICES` | list[int] | `[2, 0, 1]` |  | Webcam indices to try, in order (JSON list) |
| `CAMERA__SHOW_WINDOW` | bool | `True` |  | Show the video window; false on servers and in Docker |
| `CAMERA__RECONNECT_DELAY_S` | float | `2.0` | > 0 | Wait before reopening a lost or missing source |
| `CAMERA__MAX_FAILED_READS` | int | `50` | >= 1 | Failed reads in a row before the source is reopened |

## vision

| Variable | Type | Default | Allowed | Meaning |
|---|---|---|---|---|
| `VISION__MODEL_PATH` | str | `yolov8n.pt` |  | YOLO weights file (downloaded if missing) |
| `VISION__PERSON_CONFIDENCE_MIN` | float | `0.5` | >= 0, <= 1 | Minimum YOLO confidence for a person |
| `VISION__NMS_IOU_THRESHOLD` | float | `0.7` | >= 0, <= 1 | YOLO duplicate-box suppression overlap |
| `VISION__TRACK_IOU_THRESHOLD` | float | `0.7` | >= 0, <= 1 | Tracker: same person if box overlap is above this |
| `VISION__POSE_MODEL_COMPLEXITY` | int | `1` | >= 0, <= 2 | MediaPipe Pose model: 0 fast .. 2 accurate |
| `VISION__POSE_MIN_DETECTION_CONFIDENCE` | float | `0.5` | >= 0, <= 1 | MediaPipe detection confidence |
| `VISION__POSE_MIN_TRACKING_CONFIDENCE` | float | `0.5` | >= 0, <= 1 | MediaPipe tracking confidence |

## fall

Mirrors FallThresholds; see fall/fall_detector.py for the algorithm.

| Variable | Type | Default | Allowed | Meaning |
|---|---|---|---|---|
| `FALL__TILT_THRESHOLD_DEG` | float | `60.0` | > 0, < 180 | Torso tilt from vertical that counts as not upright |
| `FALL__LYING_MARGIN_DEG` | float | `10.0` | >= 0 | Extra tilt on top of the threshold = lying |
| `FALL__VELOCITY_THRESHOLD_PX` | float | `0.5` | >= 0 | Torso movement per frame (pixels) = falling |
| `FALL__FALLING_FRAMES` | int | `5` | >= 1 | Frames in a row tilted and moving to confirm a fall |
| `FALL__LYING_FRAMES` | int | `5` | >= 1 | Frames in a row lying to confirm a fall |
| `FALL__MIN_VISIBILITY` | float | `0.5` | >= 0, <= 1 | Shoulders and hips must be this visible |

## alerts

| Variable | Type | Default | Allowed | Meaning |
|---|---|---|---|---|
| `ALERTS__COOLDOWN_S` | float | `60.0` | >= 0 | Minimum time between two alerts for the same person |
| `ALERTS__FORGET_AFTER_S` | float | `30.0` | > 0 | Forget people/devices not seen this long (never before cooldown ends) |
| `ALERTS__QUEUE_SIZE` | int | `100` | >= 1 | Alerts waiting for delivery before new ones are dropped |
| `ALERTS__WORKERS` | int | `2` | >= 1 | Alerts delivered at the same time |
| `ALERTS__CHANNEL_TIMEOUT_S` | float | `30.0` | > 0 | Time limit for one attempt on one channel |
| `ALERTS__RETRY_ATTEMPTS` | int | `3` | >= 1 | Attempts per channel before giving up |
| `ALERTS__RETRY_BASE_DELAY_S` | float | `1.0` | >= 0 | Wait after the first failure; doubles each time |
| `ALERTS__SHUTDOWN_DRAIN_S` | float | `15.0` | >= 0 | Time to finish queued alerts when stopping |

## database

| Variable | Type | Default | Allowed | Meaning |
|---|---|---|---|---|
| `DATABASE__PATH` | Path | `fall_events.db` |  | SQLite file for fall events |

## logging

| Variable | Type | Default | Allowed | Meaning |
|---|---|---|---|---|
| `LOGGING__LEVEL` | one of: DEBUG, INFO, WARNING, ERROR | `INFO` |  | Log level |
| `LOGGING__FORMAT` | one of: text, json | `text` |  | json for log collectors (Loki, ELK) |

## health

| Variable | Type | Default | Allowed | Meaning |
|---|---|---|---|---|
| `HEALTH__ENABLED` | bool | `True` |  | Serve /health/live, /health/ready and /metrics |
| `HEALTH__HOST` | str | `127.0.0.1` |  | Bind address; 0.0.0.0 inside Docker |
| `HEALTH__PORT` | int | `8080` | >= 1, <= 65535 | HTTP port |
