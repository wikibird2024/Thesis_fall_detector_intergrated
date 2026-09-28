"""Test doubles. Each one replaces a real dependency (network, camera, model)
through the same interface the app uses, so tests are fast and deterministic."""

from __future__ import annotations

import asyncio
from collections import deque

import numpy as np

from fall_detector.domain import Alert, FallEvent
from fall_detector.vision.analyzer import TrackedPerson


class FakeClock:
    """Replaces time.monotonic; tests move time forward by hand."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class RecordingSink:
    """Stands in for AlertDispatcher.submit()."""

    def __init__(self) -> None:
        self.events: list[FallEvent] = []
        self.images: list[bytes | None] = []

    def submit(self, event: FallEvent, image_jpeg: bytes | None = None) -> bool:
        self.events.append(event)
        self.images.append(image_jpeg)
        return True


class FakeChannel:
    """Alert channel that records alerts. Can fail the first N sends, or hang."""

    def __init__(self, name: str = "fake", fail_times: int = 0, hang: bool = False) -> None:
        self.name = name
        self.fail_times = fail_times
        self.hang = hang
        self.sent: list[Alert] = []
        self.attempts = 0
        self.started = False
        self.closed = False

    async def start(self) -> None:
        self.started = True

    async def send(self, alert: Alert) -> None:
        self.attempts += 1
        if self.hang:
            await asyncio.Event().wait()  # never returns; the dispatcher timeout must stop it
        if self.attempts <= self.fail_times:
            raise ConnectionError(f"{self.name} down (attempt {self.attempts})")
        self.sent.append(alert)

    async def close(self) -> None:
        self.closed = True


class FakeAnalyzer:
    """Returns scripted people per frame, in order; then nobody."""

    def __init__(self, frames: list[list[TrackedPerson]] | None = None) -> None:
        self.frames = deque(frames or [])
        self.closed = False

    def analyze(self, frame: np.ndarray) -> list[TrackedPerson]:
        return self.frames.popleft() if self.frames else []

    def close(self) -> None:
        self.closed = True


class FakeVideoSource:
    """Yields `frame_count` black frames, then read failures."""

    def __init__(self, frame_count: int = 10, shape: tuple[int, int, int] = (240, 320, 3)) -> None:
        self.remaining = frame_count
        self.shape = shape
        self.released = False

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self.remaining <= 0:
            return False, None
        self.remaining -= 1
        return True, np.zeros(self.shape, dtype=np.uint8)

    def release(self) -> None:
        self.released = True


async def wait_until(condition, timeout_s: float = 2.0, interval_s: float = 0.01) -> None:
    """Poll until condition() is true. Fails the test on timeout."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while not condition():
        if loop.time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(interval_s)
