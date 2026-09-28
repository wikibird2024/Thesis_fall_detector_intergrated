"""Print the chat id of the last person who messaged your bot.

1. Put TELEGRAM__BOT_TOKEN in .env
2. Send /start to your bot in Telegram
3. python scripts/get_telegram_chat_id.py
4. Copy the printed id to TELEGRAM__CHAT_ID in .env
"""

import asyncio
import contextlib
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telegram import Bot
from telegram.error import TelegramError

from fall_detector.settings import apply_legacy_env_names


async def main() -> int:
    apply_legacy_env_names(Path(".env"))  # old TELEGRAM_BOT_TOKEN name still works
    load_dotenv()
    token = os.environ.get("TELEGRAM__BOT_TOKEN")
    if not token:
        print("TELEGRAM__BOT_TOKEN is not set in .env")
        return 1

    bot = Bot(token=token)
    try:
        updates = await bot.get_updates(offset=-1)
        if not updates or not updates[-1].effective_chat:
            print("No messages yet. Send /start to the bot, then run this again.")
            return 1
        chat = updates[-1].effective_chat
        print(f"Chat id:  {chat.id}")
        print(f"Username: {chat.username or '-'}")
        return 0
    except TelegramError as error:
        print(f"Telegram error: {error}")
        return 1
    finally:
        with contextlib.suppress(TelegramError):  # flood control on close is harmless here
            await bot.shutdown()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
