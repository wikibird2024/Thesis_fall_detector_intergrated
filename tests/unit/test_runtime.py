"""Retry policy and task supervisor."""

import asyncio
from datetime import timedelta

import pytest

from fakes import wait_until
from fall_detector.runtime.retry import RetryPolicy, retry_after_s, retry_async
from fall_detector.runtime.supervisor import TaskSupervisor

# ---------------------------------------------------------------- retry


def test_delay_doubles_and_is_capped():
    policy = RetryPolicy(base_delay_s=1, max_delay_s=5, jitter_ratio=0)
    assert [policy.delay_s(n) for n in range(1, 6)] == [1, 2, 4, 5, 5]


def test_jitter_stays_within_ratio():
    policy = RetryPolicy(base_delay_s=10, jitter_ratio=0.1)
    assert all(9 <= policy.delay_s(1) <= 11 for _ in range(100))


class Flaky:
    def __init__(self, failures: int, error: Exception | None = None):
        self.failures = failures
        self.calls = 0
        self.error = error or ConnectionError("down")

    async def __call__(self):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error
        return "ok"


async def test_retry_succeeds_after_failures():
    waits = []

    async def fake_sleep(seconds):
        waits.append(seconds)

    operation = Flaky(failures=2)
    result = await retry_async(
        operation, RetryPolicy(attempts=3, jitter_ratio=0), description="x", sleep=fake_sleep
    )
    assert (result, operation.calls, waits) == ("ok", 3, [1.0, 2.0])


async def test_retry_raises_last_error_when_attempts_used_up():
    operation = Flaky(failures=5)
    with pytest.raises(ConnectionError):
        await retry_async(operation, RetryPolicy(attempts=2, base_delay_s=0), description="x")
    assert operation.calls == 2


class FloodControl(Exception):
    retry_after = 7


async def test_server_retry_after_hint_is_used():
    waits = []

    async def fake_sleep(seconds):
        waits.append(seconds)

    await retry_async(Flaky(1, FloodControl()), RetryPolicy(attempts=2), description="x", sleep=fake_sleep)
    assert waits == [7.0]


@pytest.mark.parametrize(("hint", "expected"), [(3, 3.0), (timedelta(seconds=2), 2.0), (None, None)])
def test_retry_after_formats(hint, expected):
    error = Exception()
    error.retry_after = hint
    assert retry_after_s(error) == expected


# ---------------------------------------------------------------- supervisor

FAST = RetryPolicy(base_delay_s=0.001, max_delay_s=0.001)


async def test_crashing_task_is_restarted():
    runs = []

    async def crashes_twice():
        runs.append(1)
        if len(runs) <= 2:
            raise RuntimeError("boom")
        await asyncio.Event().wait()

    restarted = []
    supervisor = TaskSupervisor(FAST, on_restart=restarted.append)
    supervisor.start("worker", crashes_twice)
    await wait_until(lambda: len(runs) == 3)

    state = supervisor.states["worker"]
    assert state.restarts == 2 and state.is_running and "boom" in state.last_error
    assert restarted == ["worker", "worker"]
    await supervisor.stop()


async def test_one_task_crashing_does_not_stop_another():
    # Regression: MQTT giving up used to cancel the camera task.
    ticks = []

    async def steady():
        while True:
            ticks.append(1)
            await asyncio.sleep(0.001)

    async def broken():
        raise RuntimeError("mqtt down")

    supervisor = TaskSupervisor(FAST)
    supervisor.start("camera", steady)
    supervisor.start("mqtt", broken)
    await wait_until(lambda: supervisor.states["mqtt"].restarts >= 3)
    before = len(ticks)
    await wait_until(lambda: len(ticks) > before)
    assert supervisor.states["camera"].is_running
    await supervisor.stop()


async def test_task_without_restart_on_exit_finishes_once():
    runs = []

    async def quick():
        runs.append(1)

    supervisor = TaskSupervisor(FAST)
    supervisor.start("once", quick, restart_on_exit=False)
    await asyncio.sleep(0.05)
    assert runs == [1]


async def test_stop_by_name_leaves_others_running():
    async def forever():
        await asyncio.Event().wait()

    supervisor = TaskSupervisor(FAST)
    supervisor.start("a", forever)
    supervisor.start("b", forever)
    await asyncio.sleep(0)
    await supervisor.stop(names=["a"])
    assert supervisor.states["a"].task.done()
    assert not supervisor.states["b"].task.done()
    await supervisor.stop()


def test_duplicate_task_name_is_rejected():
    async def body():
        pass

    async def scenario():
        supervisor = TaskSupervisor(FAST)
        supervisor.start("x", body)
        with pytest.raises(ValueError):
            supervisor.start("x", body)
        await supervisor.stop()

    asyncio.run(scenario())
