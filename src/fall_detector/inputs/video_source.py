"""Video sources: ESP32-CAM MJPEG over HTTP, or a local webcam/file via OpenCV.

Both expose the same two methods (the VideoSource protocol), so the camera
pipeline does not care which one it has:

    read()    -> (True, frame) or (False, None)
    release() -> close it

The ESP32 wrapper reconnects by itself when no frame arrived for
`alive_timeout` seconds. All calls block; the pipeline runs them in a thread.
"""

from __future__ import annotations

import contextlib
import logging
import socket
import time
from collections.abc import Iterator, Sequence
from typing import Protocol
from urllib.parse import urlparse

import cv2
import numpy as np
import requests

logger = logging.getLogger(__name__)

JPEG_START = b"\xff\xd8"
JPEG_END = b"\xff\xd9"


class VideoSource(Protocol):
    def read(self) -> tuple[bool, np.ndarray | None]: ...

    def release(self) -> None: ...


class StreamError(Exception):
    pass


def resolve_mdns_or_ip(url: str) -> str:
    """Replace a `.local` (mDNS) host name with its IP; some HTTP stacks can't resolve it."""
    host = urlparse(url).hostname
    if not host or not host.endswith(".local"):
        return url
    try:
        ip = socket.gethostbyname(host)
    except OSError as error:
        logger.warning("Could not resolve %s: %s", host, error)
        return url
    logger.info("Resolved %s -> %s", host, ip)
    return url.replace(host, ip)


class ESP32StreamWrapper:
    """Reads JPEG frames from an ESP32-CAM MJPEG (multipart) HTTP stream."""

    def __init__(
        self,
        url: str,
        alive_timeout: float = 10.0,
        connect_timeout: float = 10.0,
        read_chunk_size: int = 8192,
        max_buffer: int = 2 * 1024 * 1024,
        reconnect_backoff_base: float = 0.5,
        reconnect_backoff_max: float = 8.0,
    ) -> None:
        self.url = resolve_mdns_or_ip(url)
        if urlparse(self.url).scheme not in ("http", "https"):
            raise ValueError(f"Unsupported URL scheme: {self.url}")
        self.alive_timeout = alive_timeout
        self.connect_timeout = connect_timeout
        self.read_chunk_size = read_chunk_size
        self.max_buffer = max_buffer
        self._backoff_base = reconnect_backoff_base
        self._backoff_max = reconnect_backoff_max

        self.session: requests.Session | None = None
        self.response: requests.Response | None = None
        self._chunks: Iterator[bytes] | None = None
        self.buffer = b""
        self.last_frame_time = 0.0
        self._connect_attempts = 0

        if not self.connect():
            raise StreamError(f"Failed to connect to ESP32 stream: {self.url}")

    def connect(self) -> bool:
        self._connect_attempts += 1
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update(
                {"User-Agent": "fall-detector/2", "Accept": "multipart/x-mixed-replace, image/jpeg, */*"}
            )
        self._close_response()
        try:
            logger.info("Connecting to ESP32 stream %s (attempt %d)", self.url, self._connect_attempts)
            self.response = self.session.get(self.url, stream=True, timeout=self.connect_timeout)
            self.response.raise_for_status()
            content_type = self.response.headers.get("Content-Type", "")
            if "multipart" not in content_type and "jpeg" not in content_type:
                logger.warning("Unexpected Content-Type from ESP32: %s", content_type)
            self._chunks = self.response.iter_content(chunk_size=self.read_chunk_size)
            self.buffer = b""
            self.last_frame_time = time.monotonic()
            self._connect_attempts = 0
            logger.info("ESP32 stream connected")
            return True
        except requests.RequestException as error:
            backoff = min(self._backoff_base * 2 ** (self._connect_attempts - 1), self._backoff_max)
            logger.error("ESP32 connection failed: %s; waiting %.1fs", error, backoff)
            time.sleep(backoff)
            return False

    def is_alive(self) -> bool:
        return (time.monotonic() - self.last_frame_time) < self.alive_timeout

    def read(self) -> tuple[bool, np.ndarray | None]:
        """Read chunks until one full JPEG is decoded, or give up after alive_timeout.

        Before: one call read ONE 8 KB chunk; a frame is 20-50 KB, so most calls
        returned "no frame" and the caller slept 0.3 s each time (about 1 fps).
        """
        if not self.is_alive():
            logger.info("No ESP32 frame for %.0fs; reconnecting", self.alive_timeout)
            self.connect()
        if self._chunks is None:
            return False, None

        try:
            while self.is_alive():
                frame = self._next_frame_from_buffer()
                if frame is not None:
                    self.last_frame_time = time.monotonic()
                    return True, frame
                chunk = next(self._chunks, None)
                if not chunk:
                    return False, None  # stream ended; watchdog reconnects next call
                self.buffer += chunk
                if len(self.buffer) > self.max_buffer:
                    logger.warning("ESP32 buffer overflow; dropping %d bytes", len(self.buffer))
                    self.buffer = b""
        except (requests.RequestException, OSError) as error:
            logger.warning("ESP32 stream read error: %s", error)
            self.connect()
        return False, None

    def _next_frame_from_buffer(self) -> np.ndarray | None:
        start = self.buffer.find(JPEG_START)
        end = self.buffer.find(JPEG_END, start + 2) if start != -1 else -1
        if start == -1 or end == -1:
            return None
        jpeg = self.buffer[start : end + 2]
        self.buffer = self.buffer[end + 2 :]
        return cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)

    def _close_response(self) -> None:
        if self.response is not None:
            with contextlib.suppress(Exception):
                self.response.close()
        self.response = None
        self._chunks = None

    def release(self) -> None:
        self._close_response()
        if self.session is not None:
            with contextlib.suppress(Exception):
                self.session.close()
        self.session = None
        self.buffer = b""
        logger.info("ESP32 stream released: %s", self.url)


def find_and_connect_source(sources: Sequence[str | int]) -> VideoSource | None:
    """Open the first source that works, in priority order.

    http(s) URL -> ESP32StreamWrapper;  int or file path -> cv2.VideoCapture.
    """
    for source in sources:
        logger.info("Trying video source %s", source)
        if isinstance(source, str) and source.startswith("http"):
            try:
                return ESP32StreamWrapper(source)
            except (StreamError, ValueError) as error:
                logger.warning("ESP32 stream unavailable: %s", error)
            continue
        capture = cv2.VideoCapture(source)
        if capture.isOpened():
            logger.info("Opened video source %s", source)
            return capture
        capture.release()
    logger.warning("No working video source among %s", list(sources))
    return None
