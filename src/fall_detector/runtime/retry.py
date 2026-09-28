"""Retry with exponential backoff: one implementation used everywhere.

    attempt 1 fails -> wait base        (1 s)
    attempt 2 fails -> wait base * 2    (2 s)
    attempt 3 fails -> give up, raise the last error

If the error carries a `retry_after` hint (Telegram flood control does), that
wait is used instead.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    base_delay_s: float = 1.0
    max_delay_s: float = 30.0
    jitter_ratio: float = 0.1  # +-10% so many clients don't retry in lockstep

    def delay_s(self, failed_attempt: int) -> float:
        """Wait time after the given failed attempt (1-based)."""
        delay = min(self.base_delay_s * 2 ** (failed_attempt - 1), self.max_delay_s)
        return delay * (1 + random.uniform(-self.jitter_ratio, self.jitter_ratio))


def retry_after_s(error: BaseException) -> float | None:
    """Server-requested wait, if the error has one."""
    hint = getattr(error, "retry_after", None)
    if isinstance(hint, timedelta):
        return hint.total_seconds()
    if isinstance(hint, (int, float)):
        return float(hint)
    return None


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    policy: RetryPolicy,
    *,
    description: str,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Run `operation` until it succeeds or `policy.attempts` is used up.

    `operation` is a factory (lambda: coro()) because a coroutine can only be
    awaited once. Cancellation is never retried.
    """
    for attempt in range(1, policy.attempts + 1):
        try:
            return await operation()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if attempt == policy.attempts:
                raise
            delay = retry_after_s(error) or policy.delay_s(attempt)
            logger.warning(
                "%s failed (attempt %d/%d): %r; retrying in %.1fs",
                description,
                attempt,
                policy.attempts,
                error,
                delay,
            )
            await sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover
