"""Whole application with fakes only at the edges (camera, broker, alert channel).

Real: settings, supervisor, processor, dispatcher, repository (SQLite on disk).
These tests prove the parts are wired together correctly.
"""

import asyncio
import json

import aiomqtt
import pytest

from builders import box, lying
from fakes import FakeAnalyzer, FakeChannel, FakeVideoSource, wait_until
from fall_detector.app import Application, Components
from fall_detector.inputs.mqtt_client import MQTTClient
from fall_detector.settings import Settings
from fall_detector.storage.repository import FallEventRepository
from fall_detector.vision.analyzer import TrackedPerson


def test_settings(**overrides) -> Settings:
    values = {
        "mqtt": {"enabled": False},
        "telegram": {"enabled": False},
        "ami": {"enabled": False},
        "camera": {"show_window": False, "reconnect_delay_s": 0.01},
        "fall": {"lying_frames": 3},
        "alerts": {"retry_base_delay_s": 0, "shutdown_drain_s": 2},
        "health": {"enabled": False},
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


test_settings.__test__ = False  # helper, not a test


class BrokerDown:
    """aiomqtt.Client stand-in that can never connect."""

    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        raise aiomqtt.MqttError("connection refused")

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def repository(tmp_path):
    return FallEventRepository(tmp_path / "events.db")


async def start(app: Application) -> asyncio.Task:
    task = asyncio.create_task(app.run())
    await wait_until(lambda: "alerts" in app.supervisor.states)
    return task


async def test_camera_fall_is_alerted_and_stored(repository):
    channel = FakeChannel("telegram")
    analyzer = FakeAnalyzer([[TrackedPerson(1, box(0, 0, 100, 200), lying())]] * 3)
    app = Application(test_settings(), Components(
        repository=repository, channels=[channel], analyzer=analyzer,
        open_video_source=lambda: FakeVideoSource(frame_count=50),
    ))  # fmt: skip

    task = await start(app)
    await wait_until(lambda: len(channel.sent) == 1)
    await wait_until(lambda: repository.recent() and repository.recent()[0].status == "alerted")
    app.request_stop()
    await asyncio.wait_for(task, timeout=5)

    [stored] = repository.recent()
    assert stored.entity_id == "camera_person_1"
    assert stored.event_id == channel.sent[0].event.event_id  # one id end to end
    assert channel.started and channel.closed and analyzer.closed


async def test_wearable_fall_is_alerted_while_broker_reconnects(repository):
    channel = FakeChannel()
    mqtt = MQTTClient(
        "broker", 1883, "topic", reconnect_min_s=0.01, reconnect_max_s=0.01, client_factory=BrokerDown
    )
    app = Application(test_settings(mqtt={"enabled": False}), Components(
        repository=repository, channels=[channel], mqtt_client=mqtt,
    ))  # fmt: skip

    task = await start(app)
    # The broker keeps failing and restarting; a message that did arrive is still handled.
    mqtt.handle_payload(json.dumps({"device_id": "wrist-9", "fall_detected": True}).encode())
    await wait_until(lambda: len(channel.sent) == 1)
    assert app.status()["mqtt"] == {"enabled": True, "connected": False}
    assert not app.status()["ready"]

    app.request_stop()
    await asyncio.wait_for(task, timeout=5)
    assert channel.sent[0].event.entity_id == "wrist-9"


async def test_queued_alerts_are_delivered_during_shutdown(repository):
    channel = FakeChannel()
    app = Application(test_settings(), Components(repository=repository, channels=[channel]))
    task = await start(app)
    await app.supervisor.stop(names=["alerts"])  # pause delivery so alerts pile up

    from fall_detector.domain import EventSource, FallEvent

    for n in range(3):
        app.dispatcher.submit(FallEvent(source=EventSource.WEARABLE, entity_id=f"d{n}"))
    app.supervisor.states.pop("alerts")
    app.supervisor.start("alerts", app.dispatcher.run)
    app.request_stop()
    await asyncio.wait_for(task, timeout=5)

    assert len(channel.sent) == 3


async def test_status_reports_camera_and_tasks(repository):
    app = Application(test_settings(), Components(
        repository=repository, analyzer=FakeAnalyzer(), open_video_source=lambda: FakeVideoSource(10_000),
    ))  # fmt: skip
    task = await start(app)
    await wait_until(lambda: app.status()["ready"])

    status = app.status()
    assert status["camera"]["connected"] and status["camera"]["frames"] > 0
    assert set(status["tasks"]) == {"alerts", "camera", "heartbeat"}

    app.request_stop()
    await asyncio.wait_for(task, timeout=5)
