"""The contract every alert channel follows.

A channel only knows how to deliver one alert once. Retries, timeouts,
parallel delivery and bookkeeping live in AlertDispatcher, so they are written
once and behave the same for Telegram, Asterisk, or any channel added later
(email, SMS gateway, webhook).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from fall_detector.domain import Alert


class AlertDeliveryError(Exception):
    """The channel could not deliver the alert."""


@runtime_checkable
class AlertChannel(Protocol):
    name: str

    async def start(self) -> None:
        """Connect / log in. Must not raise for network problems: log and retry on send."""

    async def send(self, alert: Alert) -> None:
        """Deliver one alert. Raise on failure; the dispatcher decides whether to retry."""

    async def close(self) -> None:
        """Release connections."""
