"""Keeps long-running tasks alive.

Before: all tasks sat in one `asyncio.wait(FIRST_COMPLETED)`, so when MQTT gave
up after 10 retries, the camera task was cancelled too and fall detection
stopped. Now each task runs on its own:

    task crashes        -> log it, wait (backoff), start it again
    task returns        -> restart it too, unless it was started with
                           restart_on_exit=False (e.g. the user pressed 'q')
    supervisor.stop()   -> cancel all tasks and wait for them

One broken input can no longer take down the others.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field

from fall_detector.runtime.retry import RetryPolicy

logger = logging.getLogger(__name__)

TaskFactory = Callable[[], Awaitable[None]]


@dataclass
class TaskState:
    name: str
    restarts: int = 0
    is_running: bool = False
    last_error: str | None = None
    task: asyncio.Task[None] | None = field(default=None, repr=False)


class TaskSupervisor:
    def __init__(
        self,
        restart_policy: RetryPolicy | None = None,
        stable_after_s: float = 60.0,
        on_restart: Callable[[str], None] | None = None,
    ) -> None:
        # attempts is unused here: the supervisor never gives up.
        self._policy = restart_policy or RetryPolicy(base_delay_s=1.0, max_delay_s=60.0)
        self._stable_after_s = stable_after_s  # run this long without crashing -> backoff resets
        self._on_restart = on_restart
        self._states: dict[str, TaskState] = {}

    @property
    def states(self) -> dict[str, TaskState]:
        return self._states

    def start(self, name: str, factory: TaskFactory, *, restart_on_exit: bool = True) -> None:
        if name in self._states:
            raise ValueError(f"task {name!r} already started")
        state = TaskState(name)
        state.task = asyncio.create_task(self._keep_running(state, factory, restart_on_exit), name=name)
        self._states[name] = state

    async def _keep_running(self, state: TaskState, factory: TaskFactory, restart_on_exit: bool) -> None:
        failures_in_a_row = 0
        while True:
            started_at = time.monotonic()
            state.is_running = True
            try:
                await factory()
                state.is_running = False
                if not restart_on_exit:
                    logger.info("Task %s finished", state.name)
                    return
                logger.warning("Task %s returned unexpectedly; restarting", state.name)
            except asyncio.CancelledError:
                state.is_running = False
                raise
            except Exception as error:
                state.is_running = False
                state.last_error = repr(error)
                logger.exception("Task %s crashed", state.name)

            if time.monotonic() - started_at >= self._stable_after_s:
                failures_in_a_row = 0
            failures_in_a_row += 1
            delay = self._policy.delay_s(failures_in_a_row)
            state.restarts += 1
            if self._on_restart:
                self._on_restart(state.name)
            logger.info("Restarting %s in %.1fs (restart #%d)", state.name, delay, state.restarts)
            await asyncio.sleep(delay)

    async def stop(self, names: Iterable[str] | None = None, timeout_s: float = 10.0) -> None:
        """Cancel the named tasks (all when names is None) and wait for them to end."""
        selected = (
            self._states.values() if names is None else [self._states[n] for n in names if n in self._states]
        )
        tasks = [s.task for s in selected if s.task and not s.task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            _, still_running = await asyncio.wait(tasks, timeout=timeout_s)
            for task in still_running:
                logger.error("Task %s did not stop within %.0fs", task.get_name(), timeout_s)
