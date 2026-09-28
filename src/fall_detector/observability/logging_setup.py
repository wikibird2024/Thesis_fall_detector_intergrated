"""Logging is configured once, here, at startup. Modules only call logging.getLogger(__name__).

text: readable lines for a terminal
    2026-09-28 10:15:02 WARNING fall_detector.alerts.dispatcher: FALL ALERT [3f9c...] ...
json: one JSON object per line, for log collectors (Loki, ELK, CloudWatch)
    {"time": "...", "level": "WARNING", "logger": "...", "message": "..."}
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

TEXT_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
NOISY_LIBRARIES = ("httpx", "httpcore", "telegram", "urllib3", "ultralytics", "panoramisk")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(level: str = "INFO", fmt: str = "text") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter() if fmt == "json" else logging.Formatter(TEXT_FORMAT, "%Y-%m-%d %H:%M:%S")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # Third-party libraries log every HTTP request at INFO; keep them quiet.
    for name in NOISY_LIBRARIES:
        logging.getLogger(name).setLevel(max(logging.WARNING, root.level))
