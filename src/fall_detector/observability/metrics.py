"""Prometheus metrics: numbers that show whether the system is healthy.

Served at http://<health host>:<port>/metrics. Grafana can graph them and
alert when, for example, no frame was processed for 1 minute or Telegram
deliveries start failing.

Naming follows Prometheus conventions: <app>_<what>_<unit>, counters end in _total.
"""

from prometheus_client import Counter, Gauge, Histogram

PREFIX = "fall_detector"

# ---- camera
FRAMES_PROCESSED = Counter(f"{PREFIX}_frames_processed_total", "Camera frames analyzed")
FRAME_SECONDS = Histogram(
    f"{PREFIX}_frame_processing_seconds",
    "Time to analyze one frame (detect + track + pose + decide)",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0),
)
PEOPLE_IN_VIEW = Gauge(f"{PREFIX}_people_in_view", "People tracked in the latest frame")
CAMERA_CONNECTED = Gauge(f"{PREFIX}_camera_connected", "1 if a video source is open")

# ---- MQTT
MQTT_CONNECTED = Gauge(f"{PREFIX}_mqtt_connected", "1 if connected to the MQTT broker")
MQTT_MESSAGES = Counter(f"{PREFIX}_mqtt_messages_total", "MQTT messages received", ["outcome"])

# ---- decisions
FALLS_DETECTED = Counter(f"{PREFIX}_falls_detected_total", "Confirmed falls, before cooldown", ["source"])
ALERTS_SUPPRESSED = Counter(
    f"{PREFIX}_alerts_suppressed_total", "Falls not alerted (cooldown or duplicate)", ["reason"]
)

# ---- alerts
ALERT_QUEUE_SIZE = Gauge(f"{PREFIX}_alert_queue_size", "Alerts waiting for delivery")
ALERTS_DROPPED = Counter(f"{PREFIX}_alerts_dropped_total", "Alerts dropped because the queue was full")
ALERTS_SENT = Counter(f"{PREFIX}_alerts_sent_total", "Alert deliveries per channel", ["channel", "outcome"])
ALERT_DELIVERY_SECONDS = Histogram(
    f"{PREFIX}_alert_delivery_seconds",
    "Time from start of delivery to success, per channel (includes retries)",
    ["channel"],
    buckets=(0.25, 0.5, 1, 2, 5, 10, 30, 60),
)
DB_WRITES = Counter(f"{PREFIX}_db_writes_total", "Fall event database writes", ["outcome"])

# ---- runtime
TASK_RESTARTS = Counter(f"{PREFIX}_task_restarts_total", "Background task restarts after a crash", ["task"])
