"""Composition root: builds every component from Settings, runs them, stops them cleanly.

This is the only module that knows about all the concrete classes. Everything
else receives what it needs through its constructor (dependency injection),
which is why tests can swap YOLO, Telegram or Asterisk for fakes.

    start:  migrate DB -> start alert channels -> start supervised tasks
            [alerts] [mqtt] [mqtt_consumer] [camera] [heartbeat]
    stop:   (Ctrl+C, SIGTERM, or 'q' in the window)
            stop inputs -> deliver queued alerts (drain) -> stop the rest -> close channels
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fall_detector.alerts.base import AlertChannel
from fall_detector.alerts.dispatcher import AlertDispatcher
from fall_detector.inputs.mqtt_client import MQTTClient
from fall_detector.inputs.video_source import VideoSource, find_and_connect_source
from fall_detector.observability import metrics
from fall_detector.processing.camera_pipeline import CameraPipeline
from fall_detector.processing.detection_processor import DetectionProcessor
from fall_detector.runtime.supervisor import TaskSupervisor
from fall_detector.settings import Settings
from fall_detector.storage.repository import FallEventRepository
from fall_detector.vision.analyzer import FrameAnalyzer

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_S = 60.0
INPUT_TASKS = ("camera", "mqtt", "mqtt_consumer")
MAX_FRAME_AGE_FOR_READY_S = 10.0


@dataclass
class Components:
    """Everything the app runs. `build_components` makes the real ones; tests pass fakes."""

    repository: FallEventRepository
    channels: list[AlertChannel] = field(default_factory=list)
    mqtt_client: MQTTClient | None = None
    analyzer: FrameAnalyzer | None = None  # None = camera disabled
    open_video_source: Callable[[], VideoSource | None] | None = None


async def build_components(settings: Settings) -> Components:
    """Create real components. Async because AMI must be created inside the running loop."""
    channels: list[AlertChannel] = []
    if settings.telegram.enabled:
        from fall_detector.alerts.telegram_bot import TelegramBot

        assert settings.telegram.bot_token and settings.telegram.chat_id  # checked by Settings
        channels.append(
            TelegramBot(
                settings.telegram.bot_token.get_secret_value(),
                settings.telegram.chat_id,
                send_startup_message=settings.telegram.send_startup_message,
            )
        )
    if settings.ami.enabled:
        from fall_detector.alerts.ami_trigger import AMITrigger

        ami = settings.ami
        assert ami.username and ami.secret
        channels.append(
            AMITrigger(
                ami.host, ami.port, ami.username, ami.secret.get_secret_value(),
                extensions=ami.extensions, caller_id=ami.caller_id, context=ami.context,
                hangup_extension=ami.hangup_extension, cleanup_delay_s=ami.cleanup_delay_s,
            )
        )  # fmt: skip

    mqtt_client = None
    if settings.mqtt.enabled:
        m = settings.mqtt
        mqtt_client = MQTTClient(
            m.host, m.port, m.topic, m.username, m.password.get_secret_value() if m.password else None,
            qos=m.qos, keepalive_s=m.keepalive_s, queue_size=m.queue_size,
            reconnect_min_s=m.reconnect_min_s, reconnect_max_s=m.reconnect_max_s,
        )  # fmt: skip

    analyzer = None
    open_video_source = None
    if settings.camera.enabled:
        logger.info("Loading vision models (YOLO %s, MediaPipe Pose)...", settings.vision.model_path)
        analyzer = await asyncio.to_thread(build_analyzer, settings)
        sources = settings.camera.sources()

        def open_video_source() -> VideoSource | None:
            return find_and_connect_source(sources)

    return Components(
        repository=FallEventRepository(settings.database.path),
        channels=channels,
        mqtt_client=mqtt_client,
        analyzer=analyzer,
        open_video_source=open_video_source,
    )


def build_analyzer(settings: Settings) -> FrameAnalyzer:
    from fall_detector.vision.analyzer import PoseFrameAnalyzer
    from fall_detector.vision.human_detector import HumanDetector
    from fall_detector.vision.person_tracker import PersonTracker
    from fall_detector.vision.skeleton_tracker import SkeletonTracker

    v = settings.vision
    return PoseFrameAnalyzer(
        HumanDetector(
            v.model_path, conf_threshold=v.person_confidence_min, iou_threshold=v.nms_iou_threshold
        ),
        PersonTracker(iou_threshold=v.track_iou_threshold),
        SkeletonTracker(
            v.pose_model_complexity, v.pose_min_detection_confidence, v.pose_min_tracking_confidence
        ),
    )


class Application:
    def __init__(self, settings: Settings, components: Components) -> None:
        self.settings = settings
        self.components = components
        self.supervisor = TaskSupervisor(
            on_restart=lambda name: metrics.TASK_RESTARTS.labels(task=name).inc()
        )
        a = settings.alerts
        self.dispatcher = AlertDispatcher(
            components.channels,
            components.repository,
            queue_size=a.queue_size,
            workers=a.workers,
            channel_timeout_s=a.channel_timeout_s,
            retry_policy=a.retry_policy(),
        )
        self.processor = DetectionProcessor(
            self.dispatcher,
            thresholds=settings.fall.thresholds(),
            cooldown_s=a.cooldown_s,
            forget_after_s=a.forget_after_s,
        )
        self.pipeline: CameraPipeline | None = None
        if components.analyzer is not None and components.open_video_source is not None:
            c = settings.camera
            self.pipeline = CameraPipeline(
                components.open_video_source,
                components.analyzer,
                self.processor,
                show_window=c.show_window,
                on_quit=self.request_stop,
                reconnect_delay_s=c.reconnect_delay_s,
                max_failed_reads=c.max_failed_reads,
            )
        self._stop_requested = asyncio.Event()
        self.started_at = time.monotonic()

    def request_stop(self) -> None:
        if not self._stop_requested.is_set():
            logger.info("Stop requested")
            self._stop_requested.set()

    async def run(self) -> None:
        self._install_signal_handlers()
        await self.start()
        try:
            await self._stop_requested.wait()
        finally:
            await self.stop()

    async def start(self) -> None:
        c = self.components
        version = await asyncio.to_thread(c.repository.migrate)
        logger.info("Database ready: %s (schema v%d)", c.repository.path, version)
        for channel in c.channels:
            await channel.start()
        logger.info("Alert channels: %s", [ch.name for ch in c.channels] or "none")

        self.supervisor.start("alerts", self.dispatcher.run)
        if c.mqtt_client is not None:
            self.supervisor.start("mqtt", c.mqtt_client.run_forever)
            self.supervisor.start("mqtt_consumer", self._consume_mqtt)
        if self.pipeline is not None:
            self.supervisor.start("camera", self.pipeline.run, restart_on_exit=False)
        self.supervisor.start("heartbeat", self._heartbeat)
        logger.info(
            "Fall detector running (camera=%s, mqtt=%s)", self.pipeline is not None, c.mqtt_client is not None
        )

    async def stop(self) -> None:
        logger.info("Shutting down...")
        await self.supervisor.stop(names=INPUT_TASKS)  # 1. no new events
        await self.dispatcher.drain(self.settings.alerts.shutdown_drain_s)  # 2. finish queued alerts
        await self.supervisor.stop()  # 3. everything else
        await self.dispatcher.close()  # 4. close channels
        if self.components.analyzer is not None:
            with contextlib.suppress(Exception):
                self.components.analyzer.close()
        logger.info("Stopped")

    async def _consume_mqtt(self) -> None:
        assert self.components.mqtt_client is not None
        queue = self.components.mqtt_client.messages
        while True:
            message = await queue.get()
            self.processor.handle_mqtt_data(message)
            self.processor.evict_stale()

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_S)
            status = self.status()
            logger.info(
                "Heartbeat: ready=%s camera=%s mqtt=%s alert_queue=%d",
                status["ready"], status["camera"], status["mqtt"], status["alerts"]["queued"],
            )  # fmt: skip

    def status(self) -> dict[str, Any]:
        """Snapshot for the heartbeat and the /health/ready endpoint."""
        now = time.monotonic()
        camera: dict[str, Any] = {"enabled": self.pipeline is not None}
        if self.pipeline is not None:
            age = None if self.pipeline.last_frame_at is None else round(now - self.pipeline.last_frame_at, 1)
            camera.update(connected=self.pipeline.is_connected, frames=self.pipeline.frames_processed,
                          last_frame_age_s=age)  # fmt: skip
        mqtt_client = self.components.mqtt_client
        mqtt: dict[str, Any] = {"enabled": mqtt_client is not None}
        if mqtt_client is not None:
            mqtt["connected"] = mqtt_client.is_connected

        tasks = {
            name: {"running": s.is_running, "restarts": s.restarts, "last_error": s.last_error}
            for name, s in self.supervisor.states.items()
        }
        camera_ok = not camera["enabled"] or (
            camera.get("last_frame_age_s") is not None
            and camera["last_frame_age_s"] < MAX_FRAME_AGE_FOR_READY_S
        )
        mqtt_ok = not mqtt["enabled"] or mqtt["connected"]
        alerts_ok = tasks.get("alerts", {}).get("running", False)
        return {
            "ready": bool(camera_ok and mqtt_ok and alerts_ok),
            "uptime_s": round(now - self.started_at),
            "camera": camera,
            "mqtt": mqtt,
            "alerts": {
                "queued": self.dispatcher.pending,
                "channels": [c.name for c in self.dispatcher.channels],
            },
            "tasks": tasks,
        }

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            # Not available on Windows or outside the main thread; Ctrl+C then raises KeyboardInterrupt.
            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(sig, self.request_stop)


async def run(settings: Settings) -> None:
    components = await build_components(settings)
    await Application(settings, components).run()
