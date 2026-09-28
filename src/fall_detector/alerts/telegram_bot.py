"""Telegram alert channel: photo with caption when a snapshot exists, text otherwise."""

from __future__ import annotations

import logging
from typing import Any

from telegram import Bot
from telegram.error import TelegramError

from fall_detector.domain import Alert

logger = logging.getLogger(__name__)

CAPTION_LIMIT = 1024  # Telegram's maximum photo caption length


class TelegramBot:
    name = "telegram"

    def __init__(
        self, token: str, chat_id: str, *, send_startup_message: bool = True, bot: Any = None
    ) -> None:
        self._bot = bot or Bot(token=token)  # `bot` lets tests pass a fake
        self._chat_id = chat_id
        self._send_startup_message = send_startup_message

    async def start(self) -> None:
        try:
            await self._bot.initialize()  # checks the token early
            if self._send_startup_message:
                await self.send_text("✅ Fall detector started.")
            logger.info("Telegram ready")
        except TelegramError as error:
            logger.warning("Telegram not reachable at startup (%s); will retry on first alert", error)

    async def send(self, alert: Alert) -> None:
        if alert.image_jpeg:
            try:
                await self._bot.send_photo(
                    chat_id=self._chat_id, photo=alert.image_jpeg, caption=alert.message[:CAPTION_LIMIT]
                )
                return
            except TelegramError as error:
                # A photo problem must not cost us the alert: fall back to text.
                logger.warning("Telegram photo failed (%s); sending text only", error)
        await self.send_text(alert.message)

    async def send_text(self, text: str) -> None:
        await self._bot.send_message(chat_id=self._chat_id, text=text)

    async def close(self) -> None:
        try:
            await self._bot.shutdown()
        except TelegramError as error:
            logger.debug("Telegram shutdown: %s", error)
