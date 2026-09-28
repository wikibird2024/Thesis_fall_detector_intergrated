"""Asterisk alert channel over AMI (Asterisk Manager Interface).

For every configured extension, at the same time:
  - Originate: ring the phone; the call goes to `hangup_extension` in the
    dialplan, which plays the alert and hangs up.
  - MessageSend: SIP text message with the alert.

The alert counts as delivered if at least one extension got a call or a message.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from typing import Any

from fall_detector.alerts.base import AlertDeliveryError
from fall_detector.domain import Alert

logger = logging.getLogger(__name__)


def _default_manager_factory(**kwargs: Any) -> Any:
    from panoramisk.manager import Manager  # imported here so tests don't need Asterisk libs

    return Manager(**kwargs)


def one_line(text: str) -> str:
    """AMI header values end at a line break, so multi-line text must be joined."""
    return " | ".join(line.strip() for line in text.splitlines() if line.strip())


def is_success(response: Any) -> bool:
    """AMI replies are a Message (dict-like) or a list of them."""
    if isinstance(response, list):
        return any(is_success(item) for item in response)
    status = response.get("Response", "") if hasattr(response, "get") else getattr(response, "Response", "")
    return str(status).lower() == "success"


class AMITrigger:
    name = "asterisk"

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        secret: str,
        *,
        extensions: Sequence[str],
        caller_id: str,
        context: str = "internal",
        hangup_extension: str = "9999",
        cleanup_delay_s: float = 3.0,
        manager_factory: Callable[..., Any] = _default_manager_factory,
    ) -> None:
        self.host = host
        self.port = port
        self.extensions = list(extensions)
        self.caller_id = caller_id
        self.context = context
        self.hangup_extension = hangup_extension
        self.cleanup_delay_s = cleanup_delay_s
        self._manager = manager_factory(host=host, port=port, username=username, secret=secret)
        self.is_connected = False
        self._connect_lock = asyncio.Lock()

    async def start(self) -> None:
        try:
            await self._connect()
        except Exception as error:
            logger.warning("Asterisk AMI not reachable at startup (%r); will retry on first alert", error)

    async def _connect(self) -> None:
        async with self._connect_lock:  # two alerts at once must not open two connections
            if self.is_connected:
                return
            logger.info("Connecting to Asterisk AMI at %s:%s", self.host, self.port)
            await self._manager.connect()
            self.is_connected = True
            logger.info("Asterisk AMI connected")

    async def send(self, alert: Alert) -> None:
        try:
            await self._connect()
        except Exception as error:
            raise AlertDeliveryError(f"AMI connect failed: {error!r}") from error

        results = await asyncio.gather(
            *(self._alert_extension(ext, alert.message) for ext in self.extensions)
        )
        reached = [ext for ext, ok in zip(self.extensions, results, strict=True) if ok]

        # Give Asterisk time to clean up channels before the next alert.
        await asyncio.sleep(self.cleanup_delay_s)

        if not reached:
            raise AlertDeliveryError(f"no extension reached out of {self.extensions}")
        if len(reached) < len(self.extensions):
            logger.warning("Asterisk reached only %s of %s", reached, self.extensions)

    async def _alert_extension(self, extension: str, message: str) -> bool:
        call_ok, text_ok = await asyncio.gather(
            self._originate_call(extension, message), self._send_message(extension, message)
        )
        return call_ok or text_ok

    async def _originate_call(self, extension: str, message: str) -> bool:
        return await self._action(
            f"call {extension}",
            {
                "Action": "Originate",
                "Channel": f"PJSIP/{extension}",
                "Context": self.context,
                "Exten": self.hangup_extension,
                "Priority": 1,
                "CallerID": self.caller_id,
                "Variable": f"ALERT_MSG={one_line(message)}",
                "Async": "true",
            },
        )

    async def _send_message(self, extension: str, message: str) -> bool:
        return await self._action(
            f"message {extension}",
            {
                "Action": "MessageSend",
                "To": f"pjsip:{extension}",
                "From": "server",
                "Body": one_line(message),
            },
        )

    async def _action(self, description: str, action: dict[str, Any]) -> bool:
        try:
            response = await self._manager.send_action(action)
        except Exception as error:
            logger.error("Asterisk %s failed: %r", description, error)
            self.is_connected = False  # reconnect on next alert
            return False
        ok = is_success(response)
        log = logger.info if ok else logger.warning
        log("Asterisk %s: %s", description, "ok" if ok else f"failed ({response!r})")
        return ok

    async def close(self) -> None:
        if self.is_connected:
            self._manager.close()
            self.is_connected = False
            logger.info("Asterisk AMI disconnected")
