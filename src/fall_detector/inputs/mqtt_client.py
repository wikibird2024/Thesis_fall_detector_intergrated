"""Wearable (ESP32) fall messages over MQTT.

    broker --> MQTTClient.run_forever() --parse + validate--> queue --> app consumer

- Reconnects forever with exponential backoff (1s, 2s, 4s ... max 60s).
  The old client stopped after 10 tries, which then shut down the camera too.
- Payloads are validated with a pydantic model (the "wire contract"), so bad
  data is rejected at the edge and the rest of the code can trust the types.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

import aiomqtt
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from fall_detector.observability import metrics
from fall_detector.runtime.retry import RetryPolicy

logger = logging.getLogger(__name__)


class DeviceFallMessage(BaseModel):
    """JSON the wearable publishes, e.g.
    {"device_id": "wrist-01", "fall_detected": true, "timestamp": 1700000000,
     "latitude": 10.77, "longitude": 106.70, "has_gps_fix": true}
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    device_id: str = Field(min_length=1)
    fall_detected: bool = False  # accepts true/false, 1/0, "yes"/"no", "on"/"off"
    timestamp: float | None = None  # device time; used to drop duplicate deliveries
    latitude: float | None = None
    longitude: float | None = None
    has_gps_fix: bool = False

    @model_validator(mode="before")
    @classmethod
    def _unusable_location_is_unknown(cls, data: Any) -> Any:
        # Safety first: bad GPS must not cost us the fall alert, so it becomes "unknown".
        if not isinstance(data, dict):
            return data
        lat, lon = _to_float_or_none(data.get("latitude")), _to_float_or_none(data.get("longitude"))
        if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
            return {**data, "latitude": lat, "longitude": lon}
        return {**data, "latitude": None, "longitude": None, "has_gps_fix": False}


def _to_float_or_none(value: Any) -> float | None:
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None


def parse_payload(payload: bytes | str) -> DeviceFallMessage:
    """Raises ValueError for invalid JSON or a message that breaks the contract."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ValueError(f"not JSON: {error}") from error
    if not isinstance(data, dict):
        raise ValueError(f"expected a JSON object, got {type(data).__name__}")
    try:
        return DeviceFallMessage.model_validate(data)
    except ValidationError as error:
        raise ValueError(str(error)) from error


class MQTTClient:
    def __init__(
        self,
        host: str,
        port: int,
        topic: str,
        username: str | None = None,
        password: str | None = None,
        *,
        qos: int = 0,
        keepalive_s: int = 60,
        queue_size: int = 1000,
        reconnect_min_s: float = 1.0,
        reconnect_max_s: float = 60.0,
        client_factory: Callable[..., Any] = aiomqtt.Client,
    ) -> None:
        self.host = host
        self.port = port
        self.topic = topic
        self._username = username
        self._password = password
        self._qos = qos
        self._keepalive_s = keepalive_s
        self._reconnect = RetryPolicy(base_delay_s=reconnect_min_s, max_delay_s=reconnect_max_s)
        self._client_factory = client_factory
        self.messages: asyncio.Queue[DeviceFallMessage] = asyncio.Queue(maxsize=queue_size)
        self.is_connected = False

    async def run_forever(self) -> None:
        """Connect, subscribe, read. On any connection error: wait and reconnect. Never gives up."""
        failures = 0
        while True:
            try:
                async with self._client_factory(
                    hostname=self.host,
                    port=self.port,
                    username=self._username,
                    password=self._password,
                    keepalive=self._keepalive_s,
                ) as client:
                    await client.subscribe(self.topic, qos=self._qos)
                    self._set_connected(True)
                    failures = 0
                    logger.info("MQTT connected to %s:%s, subscribed to %s", self.host, self.port, self.topic)
                    async for message in client.messages:
                        self.handle_payload(message.payload)
                # Message stream ended without an error: treat as a disconnect.
                raise aiomqtt.MqttError("message stream ended")
            except aiomqtt.MqttError as error:
                self._set_connected(False)
                failures += 1
                delay = self._reconnect.delay_s(failures)
                logger.warning("MQTT disconnected (%s); reconnecting in %.1fs", error, delay)
                await asyncio.sleep(delay)
            finally:
                self._set_connected(False)

    def _set_connected(self, connected: bool) -> None:
        self.is_connected = connected
        metrics.MQTT_CONNECTED.set(1 if connected else 0)

    def handle_payload(self, payload: Any) -> None:
        """Validate one raw payload and queue it. Never raises."""
        raw = payload if isinstance(payload, (bytes, str)) else str(payload)
        try:
            message = parse_payload(raw)
        except ValueError as error:
            logger.warning("MQTT message rejected: %s | payload=%r", error, raw[:200])
            metrics.MQTT_MESSAGES.labels(outcome="invalid").inc()
            return
        try:
            self.messages.put_nowait(message)
        except asyncio.QueueFull:
            logger.error("MQTT queue full; message from %s dropped", message.device_id)
            metrics.MQTT_MESSAGES.labels(outcome="dropped").inc()
            return
        logger.debug("MQTT message queued: %s", message)
        metrics.MQTT_MESSAGES.labels(outcome="accepted").inc()
