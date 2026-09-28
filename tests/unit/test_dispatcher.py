"""AlertDispatcher: parallel delivery, retries, timeouts, database status, draining."""

import asyncio

import pytest

from fakes import FakeChannel, wait_until
from fall_detector.alerts.dispatcher import AlertDispatcher
from fall_detector.domain import Alert, EventSource, FallEvent
from fall_detector.runtime.retry import RetryPolicy
from fall_detector.storage.repository import FallEventRepository

NO_WAIT = RetryPolicy(attempts=3, base_delay_s=0)


@pytest.fixture
def repository(tmp_path):
    repo = FallEventRepository(tmp_path / "events.db")
    repo.migrate()
    return repo


def an_event() -> FallEvent:
    return FallEvent(source=EventSource.WEARABLE, entity_id="wrist-01")


def dispatcher_with(*channels, repository=None, **kwargs) -> AlertDispatcher:
    kwargs.setdefault("retry_policy", NO_WAIT)
    return AlertDispatcher(list(channels), repository, **kwargs)


async def test_alert_goes_to_every_channel_and_is_marked_alerted(repository):
    telegram, asterisk = FakeChannel("telegram"), FakeChannel("asterisk")
    dispatcher = dispatcher_with(telegram, asterisk, repository=repository)
    event = an_event()

    assert await dispatcher.deliver(Alert(event))

    assert len(telegram.sent) == len(asterisk.sent) == 1
    [stored] = repository.recent()
    assert (stored.event_id, stored.status) == (event.event_id, "alerted")


async def test_failing_channel_is_retried_and_does_not_block_others():
    flaky, healthy = FakeChannel("flaky", fail_times=2), FakeChannel("healthy")
    dispatcher = dispatcher_with(flaky, healthy)

    assert await dispatcher.deliver(Alert(an_event()))
    assert flaky.attempts == 3 and len(flaky.sent) == 1
    assert len(healthy.sent) == 1


async def test_all_channels_failing_marks_event_alert_failed(repository):
    dispatcher = dispatcher_with(FakeChannel("down", fail_times=99), repository=repository)

    assert not await dispatcher.deliver(Alert(an_event()))
    assert repository.recent()[0].status == "alert_failed"


async def test_hanging_channel_is_cut_by_timeout():
    stuck, healthy = FakeChannel("stuck", hang=True), FakeChannel("healthy")
    dispatcher = dispatcher_with(stuck, healthy, channel_timeout_s=0.05, retry_policy=RetryPolicy(attempts=1))

    assert await asyncio.wait_for(dispatcher.deliver(Alert(an_event())), timeout=2)
    assert len(healthy.sent) == 1


async def test_alert_is_sent_even_when_database_is_broken(tmp_path):
    # Regression: in version 1 a failed insert returned early and nobody was alerted.
    broken = FallEventRepository(tmp_path / "missing-dir" / "no-migrate.db")  # never migrated: no table
    channel = FakeChannel()
    dispatcher = dispatcher_with(channel, repository=broken)

    assert await dispatcher.deliver(Alert(an_event()))
    assert len(channel.sent) == 1


async def test_submit_returns_immediately_and_worker_delivers():
    channel = FakeChannel()
    dispatcher = dispatcher_with(channel)
    worker = asyncio.create_task(dispatcher.run())
    try:
        assert dispatcher.submit(an_event(), image_jpeg=b"jpeg")
        await wait_until(lambda: len(channel.sent) == 1)
        assert channel.sent[0].image_jpeg == b"jpeg"
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)


def test_submit_reports_full_queue():
    dispatcher = dispatcher_with(FakeChannel(), queue_size=1)
    assert dispatcher.submit(an_event())
    assert not dispatcher.submit(an_event())


async def test_drain_waits_for_queued_alerts():
    channel = FakeChannel()
    dispatcher = dispatcher_with(channel)
    for _ in range(3):
        dispatcher.submit(an_event())
    worker = asyncio.create_task(dispatcher.run())
    try:
        await dispatcher.drain(timeout_s=2)
        assert len(channel.sent) == 3
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)


async def test_close_closes_all_channels():
    channels = [FakeChannel("a"), FakeChannel("b")]
    await dispatcher_with(*channels).close()
    assert all(c.closed for c in channels)
