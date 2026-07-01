"""
Features:
- Robust parsing of MJPEG stream (chunked JPEG handling)
- Persistent HTTP session (requests.Session)
- Auto reconnect with exponential backoff
- Buffer overflow protection
- Alive watchdog
- mDNS resolution + IP fallback
- Project-level config integration
- Compatible with legacy main.py

Usage:
    from esp32_stream import find_and_connect_source
    cap = find_and_connect_source()
"""

from __future__ import annotations

import time
import logging
import socket
from typing import Optional, Tuple, Union, List
from urllib.parse import urlparse

import requests
import numpy as np
import cv2

from config import config  # ✅ project-level configuration

# ---------------- Logger ----------------
logger = logging.getLogger("esp32_stream")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# ---------------- Constants ----------------
JPEG_START = b'\xff\xd8'
JPEG_END = b'\xff\xd9'


# ---------------- Exceptions ----------------
class StreamError(Exception):
    pass


# ---------------- Utility: mDNS/IP resolution ----------------
def resolve_mdns_or_ip(url: str) -> str:
    """Resolve mDNS (.local) hostname to IP address if needed."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        if host and host.endswith(".local"):
            logger.info(f"[mDNS] Resolving {host}...")
            ip = socket.gethostbyname(host)
            new_url = url.replace(host, ip)
            logger.info(f"[mDNS] Resolved {host} → {ip}")
            return new_url
        return url
    except Exception as e:
        logger.warning(f"[mDNS] Failed to resolve {url}: {e}")
        return url


# ---------------- Core Wrapper ----------------
class ESP32StreamWrapper:
    """Wrapper for ESP32-CAM MJPEG HTTP stream."""

    def __init__(
        self,
        url: str,
        alive_timeout: float = 10.0,
        connect_timeout: float = 10.0,
        read_chunk_size: int = 8192,
        max_buffer: int = 2 * 1024 * 1024,
        reconnect_backoff_base: float = 0.5,
        reconnect_backoff_max: float = 8.0,
    ):
        self.url = resolve_mdns_or_ip(url)
        self.alive_timeout = float(alive_timeout)
        self.connect_timeout = float(connect_timeout)
        self.read_chunk_size = int(read_chunk_size)
        self.max_buffer = int(max_buffer)
        self._backoff_base = float(reconnect_backoff_base)
        self._backoff_max = float(reconnect_backoff_max)

        self.session: Optional[requests.Session] = None
        self.response: Optional[requests.Response] = None
        self._iter = None
        self.bytes_buffer = b''
        self.last_frame_time = 0.0
        self._connected_at = 0.0
        self._connect_attempts = 0

        parsed = urlparse(self.url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")

        if not self.connect():
            raise StreamError(f"Failed to connect to ESP32 stream: {self.url}")

    # ---------------- Connection ----------------
    def _make_session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update({
            "User-Agent": "esp32-mjpeg-client/1.1",
            "Accept": "multipart/x-mixed-replace, image/jpeg, */*",
            "Connection": "keep-alive",
        })
        return s

    def connect(self) -> bool:
        self._connect_attempts += 1
        backoff = min(self._backoff_base * (2 ** (self._connect_attempts - 1)), self._backoff_max)

        if self.session is None:
            self.session = self._make_session()
        if self.response is not None:
            try:
                self.response.close()
            except Exception:
                pass

        try:
            logger.info(f"[ESP32] Connecting to {self.url} (attempt {self._connect_attempts})")
            self.response = self.session.get(self.url, stream=True, timeout=self.connect_timeout)
            self.response.raise_for_status()
            ctype = self.response.headers.get("Content-Type", "")
            if "multipart" not in ctype and "jpeg" not in ctype:
                logger.warning(f"[ESP32] Unexpected Content-Type: {ctype}")

            self._iter = self.response.iter_content(chunk_size=self.read_chunk_size)
            self.bytes_buffer = b''
            self.last_frame_time = time.time()
            self._connected_at = time.time()
            self._connect_attempts = 0
            logger.info(f"[ESP32] Connected successfully to {self.url}")
            return True
        except requests.RequestException as e:
            logger.error(f"[ESP32] Connection failed: {e}. Backoff {backoff:.1f}s")
            time.sleep(backoff)
            return False

    def release(self):
        if self.response:
            try: self.response.close()
            except Exception: pass
        if self.session:
            try: self.session.close()
            except Exception: pass
        self._iter = None
        self.response = None
        self.session = None
        self.bytes_buffer = b''
        logger.info(f"[ESP32] Stream released: {self.url}")

    # ---------------- Reading ----------------
    def is_alive(self) -> bool:
        return (time.time() - self.last_frame_time) < self.alive_timeout

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        # Nâng cấp log từ debug lên info để dễ theo dõi sự kiện reconnect quan trọng
        if not self.is_alive():
            logger.info("[ESP32] Alive timeout expired; attempting reconnect.")
            self.connect()

        if self._iter is None and self.response:
            self._iter = self.response.iter_content(chunk_size=self.read_chunk_size)

        try:
            chunk = next(self._iter, None)
            
            # REFACTOR: Loại bỏ self.connect() khi không có chunk để tránh spam log.
            # Logic Alive Watchdog sẽ xử lý việc reconnect sau timeout (10s).
            if not chunk:
                return False, None

            self.bytes_buffer += chunk
            if len(self.bytes_buffer) > self.max_buffer:
                self.bytes_buffer = b''
                logger.warning("[ESP32] Buffer overflow, resetting buffer.")

            start = self.bytes_buffer.find(JPEG_START)
            end = self.bytes_buffer.find(JPEG_END)
            if start != -1 and end != -1 and end > start:
                jpg = self.bytes_buffer[start:end + 2]
                self.bytes_buffer = self.bytes_buffer[end + 2:]
                arr = np.frombuffer(jpg, np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is not None:
                    self.last_frame_time = time.time()
                    return True, img
        except Exception as e:
            # Vẫn gọi connect() khi có ngoại lệ thực sự xảy ra trong quá trình đọc
            logger.warning(f"[ESP32] Stream read error: {e}")
            self.connect()
        return False, None

    # ---------------- Context Manager ----------------
    def __enter__(self) -> ESP32StreamWrapper:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


# ---------------- Helpers ----------------
def get_config_sources() -> List[Union[str, int]]:
    """Load video sources from config.py instead of .env."""
    sources: List[Union[str, int]] = []
    stream = getattr(config, "VIDEO_STREAM_URL", None)
    webcam = getattr(config, "VIDEO_WEBCAM_INDEX", None)
    if stream: sources.append(stream)
    if webcam is not None: sources.append(int(webcam))
    if not sources: sources.append(0)
    return sources


def find_and_connect_source(priority_sources: Optional[List[Union[str, int]]] = None
) -> Optional[Union[ESP32StreamWrapper, cv2.VideoCapture]]:
    """
    Try all sources in priority order:
    - HTTP/mDNS URL → ESP32StreamWrapper
    - Webcam index or file → cv2.VideoCapture
    """
    sources = priority_sources or get_config_sources()
    for src in sources:
        logger.info(f"[VIDEO] Trying source: {src}")
        if isinstance(src, str) and src.startswith("http"):
            try:
                wrapper = ESP32StreamWrapper(src)
                return wrapper
            except Exception as e:
                logger.error(f"[VIDEO] ESP32 stream failed: {e}")
        else:
            try:
                cap = cv2.VideoCapture(src)
                if cap.isOpened():
                    logger.info(f"[VIDEO] Opened local camera: {src}")
                    return cap
                cap.release()
            except Exception as e:
                logger.error(f"[VIDEO] Webcam error {src}: {e}")
    logger.error("[VIDEO] No valid video source found.")
    return None


# ---------------- Quick test ----------------
if __name__ == "__main__":
    cap = find_and_connect_source()
    if cap is None:
        logger.error("No video source found. Exiting.")
        exit(1)

    logger.info("Press ESC to exit.")
    while True:
        ok, frame = cap.read() if hasattr(cap, "read") else (False, None)
        if not ok or frame is None:
            # REFACTOR: Tăng thời gian chờ lên 0.3s để tránh spam log và giảm tải CPU
            time.sleep(0.3) 
            continue
        cv2.imshow("ESP32 Stream", frame)
        if cv2.waitKey(1) & 0xFF == 27:
            break

    if hasattr(cap, "release"):
        cap.release()
    cv2.destroyAllWindows()
