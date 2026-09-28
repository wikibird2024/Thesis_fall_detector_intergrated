"""Camera loop: open source -> read frame -> analyze -> decide -> (show).

    +-> open first working source ---- none? wait, try again
    |        |
    |   read frame (thread) --- too many failed reads in a row? --+
    |        |                                                    |
    |   analyze (thread): people + skeletons                      |
    |        |                                                    |
    |   DetectionProcessor per person (never waits on network)    |
    |        |                                                    |
    |   optional window; 'q' asks the app to stop                 |
    +---------------------- release source <----------------------+

Blocking work (camera read, YOLO, MediaPipe) runs in a worker thread so the
event loop stays free for MQTT, alerts and the health endpoint.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

import cv2
import numpy as np

from fall_detector.inputs.video_source import VideoSource
from fall_detector.observability import metrics
from fall_detector.processing.detection_processor import DetectionProcessor, camera_entity_id
from fall_detector.vision.analyzer import FrameAnalyzer
from fall_detector.vision.drawing import draw_person

logger = logging.getLogger(__name__)

WINDOW_TITLE = "Fall Detection"
FAILED_READ_PAUSE_S = 0.05
PROGRESS_LOG_EVERY_FRAMES = 1000


class CameraPipeline:
    def __init__(
        self,
        open_source: Callable[[], VideoSource | None],
        analyzer: FrameAnalyzer,
        processor: DetectionProcessor,
        *,
        show_window: bool = False,
        on_quit: Callable[[], None] | None = None,
        reconnect_delay_s: float = 2.0,
        max_failed_reads: int = 50,
    ) -> None:
        self.open_source = open_source
        self.analyzer = analyzer
        self.processor = processor
        self.show_window = show_window
        self.on_quit = on_quit
        self.reconnect_delay_s = reconnect_delay_s
        self.max_failed_reads = max_failed_reads
        self.frames_processed = 0
        self.last_frame_at: float | None = None  # monotonic time, read by the health check
        self.is_connected = False

    async def run(self) -> None:
        """Runs until cancelled, or until the user presses 'q' in the window."""
        while True:
            source = await asyncio.to_thread(self.open_source)
            if source is None:
                await asyncio.sleep(self.reconnect_delay_s)
                continue
            self._set_connected(True)
            try:
                if await self._process(source) == "quit":
                    return
            finally:
                self._set_connected(False)
                await asyncio.to_thread(source.release)
                self._close_window()
            logger.warning("Video source lost; reopening in %.1fs", self.reconnect_delay_s)
            await asyncio.sleep(self.reconnect_delay_s)

    async def _process(self, source: VideoSource) -> str:
        """Process frames until the source fails ("lost") or the user quits ("quit")."""
        failed_reads = 0
        while True:
            ok, frame = await asyncio.to_thread(source.read)
            if not ok or frame is None:
                failed_reads += 1
                if failed_reads >= self.max_failed_reads:
                    return "lost"
                await asyncio.sleep(FAILED_READ_PAUSE_S)
                continue
            failed_reads = 0

            await self.process_frame(frame)

            if self.show_window and self._show(frame):
                logger.info("'q' pressed in the video window; stopping")
                if self.on_quit:
                    self.on_quit()
                return "quit"

    async def process_frame(self, frame: np.ndarray) -> None:
        started = time.monotonic()
        people = await asyncio.to_thread(self.analyzer.analyze, frame)
        for person in people:
            is_fall = self.processor.handle_camera_data(frame, person.person_id, person.box, person.landmarks)
            if self.show_window:
                draw_person(frame, person.box, person.landmarks, camera_entity_id(person.person_id), is_fall)
        self.processor.evict_stale()

        self.frames_processed += 1
        self.last_frame_at = time.monotonic()
        metrics.FRAMES_PROCESSED.inc()
        metrics.FRAME_SECONDS.observe(self.last_frame_at - started)
        metrics.PEOPLE_IN_VIEW.set(len(people))
        if self.frames_processed % PROGRESS_LOG_EVERY_FRAMES == 0:
            logger.info("Camera: %d frames processed", self.frames_processed)

    def _set_connected(self, connected: bool) -> None:
        self.is_connected = connected
        metrics.CAMERA_CONNECTED.set(1 if connected else 0)

    def _show(self, frame: np.ndarray) -> bool:
        """Show the frame; returns True if 'q' was pressed."""
        cv2.imshow(WINDOW_TITLE, frame)
        return (cv2.waitKey(1) & 0xFF) == ord("q")

    def _close_window(self) -> None:
        if self.show_window:
            cv2.destroyAllWindows()
