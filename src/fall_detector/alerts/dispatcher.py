"""Delivers fall alerts without ever blocking detection.

    DetectionProcessor --submit()--> [queue] --> worker --+--> save to database --+
         (returns at once)                                 +--> Telegram (retry)   +--> set status:
                                                           +--> Asterisk (retry) --+    alerted / alert_failed

Rules that matter for a safety system:
  * submit() never waits: the camera keeps processing frames while alerts go out.
  * Channels and the database run in parallel. A slow or broken one does not
    delay the others; a database failure never stops an alert (it used to).
  * Every channel attempt has a timeout and a retry policy.
  * On shutdown, queued alerts get `drain()` time to finish before exit.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence

from fall_detector.alerts.base import AlertChannel
from fall_detector.domain import Alert, EventStatus, FallEvent
from fall_detector.observability import metrics
from fall_detector.runtime.retry import RetryPolicy, retry_async
from fall_detector.storage.repository import FallEventRepository

logger = logging.getLogger(__name__)


class AlertDispatcher:
    def __init__(
        self,
        channels: Sequence[AlertChannel],
        repository: FallEventRepository | None = None,
        *,
        queue_size: int = 100,
        workers: int = 2,
        channel_timeout_s: float = 30.0,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self.channels = list(channels)
        self.repository = repository
        self.channel_timeout_s = channel_timeout_s
        self.retry_policy = retry_policy or RetryPolicy()
        self._queue: asyncio.Queue[Alert] = asyncio.Queue(maxsize=queue_size)
        self._workers = workers
        if not self.channels:
            logger.warning("No alert channel is enabled: falls will only be logged and stored")

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    def submit(self, event: FallEvent, image_jpeg: bytes | None = None) -> bool:
        """Queue an alert. Returns False (and logs) if the queue is full."""
        alert = Alert(event=event, image_jpeg=image_jpeg)
        # Always leave a trace in the log, whatever happens to the channels.
        logger.warning("FALL ALERT [%s] %s", event.event_id, alert.message.replace("\n", " | "))
        try:
            self._queue.put_nowait(alert)
        except asyncio.QueueFull:
            logger.error("Alert queue full (%d); alert %s dropped", self._queue.maxsize, event.event_id)
            metrics.ALERTS_DROPPED.inc()
            return False
        metrics.ALERT_QUEUE_SIZE.set(self._queue.qsize())
        return True

    async def run(self) -> None:
        """Worker loop. Runs until cancelled."""
        await asyncio.gather(*(self._worker() for _ in range(self._workers)))

    async def _worker(self) -> None:
        while True:
            alert = await self._queue.get()
            try:
                await self.deliver(alert)
            except Exception:
                logger.exception("Unexpected error delivering alert %s", alert.event.event_id)
            finally:
                self._queue.task_done()
                metrics.ALERT_QUEUE_SIZE.set(self._queue.qsize())

    async def deliver(self, alert: Alert) -> bool:
        """Save + send on every channel in parallel. Returns True if any channel delivered."""
        event_id = alert.event.event_id
        save_task = asyncio.create_task(self._save(alert.event))
        results = await asyncio.gather(*(self._send(channel, alert) for channel in self.channels))
        delivered = any(results)
        if await save_task:
            status = EventStatus.ALERTED if delivered else EventStatus.ALERT_FAILED
            await self._set_status(event_id, status)
        if delivered:
            logger.info(
                "Alert %s delivered via %s",
                event_id,
                [c.name for c, ok in zip(self.channels, results, strict=True) if ok],
            )
        else:
            logger.error("Alert %s was NOT delivered on any channel", event_id)
        return delivered

    async def _send(self, channel: AlertChannel, alert: Alert) -> bool:
        started = time.monotonic()
        try:
            await retry_async(
                lambda: asyncio.wait_for(channel.send(alert), timeout=self.channel_timeout_s),
                self.retry_policy,
                description=f"{channel.name} alert {alert.event.event_id}",
            )
        except Exception as error:
            logger.error("%s alert %s failed after retries: %r", channel.name, alert.event.event_id, error)
            metrics.ALERTS_SENT.labels(channel=channel.name, outcome="failed").inc()
            return False
        metrics.ALERTS_SENT.labels(channel=channel.name, outcome="ok").inc()
        metrics.ALERT_DELIVERY_SECONDS.labels(channel=channel.name).observe(time.monotonic() - started)
        return True

    async def _save(self, event: FallEvent) -> bool:
        if self.repository is None:
            return False
        repository = self.repository
        try:
            await retry_async(
                lambda: asyncio.to_thread(repository.save, event),
                self.retry_policy,
                description=f"save event {event.event_id}",
            )
        except Exception as error:
            logger.error("Could not save event %s: %r", event.event_id, error)
            metrics.DB_WRITES.labels(outcome="failed").inc()
            return False
        metrics.DB_WRITES.labels(outcome="ok").inc()
        return True

    async def _set_status(self, event_id: str, status: EventStatus) -> None:
        assert self.repository is not None
        try:
            await asyncio.to_thread(self.repository.set_status, event_id, status)
        except Exception as error:
            logger.error("Could not update status of event %s: %r", event_id, error)

    async def drain(self, timeout_s: float) -> None:
        """Wait for queued alerts to finish, up to timeout_s. Call before stopping workers."""
        if self._queue.qsize():
            logger.info("Finishing %d queued alert(s) before exit...", self._queue.qsize())
        try:
            await asyncio.wait_for(self._queue.join(), timeout=timeout_s)
        except asyncio.TimeoutError:
            logger.error("Stopped with %d alert(s) not delivered", self._queue.qsize())

    async def close(self) -> None:
        for channel in self.channels:
            try:
                await channel.close()
            except Exception as error:
                logger.warning("Closing %s failed: %r", channel.name, error)
