"""Manual check: connect to the real MQTT broker and print every valid fall message.

    python scripts/manual/mqtt_test.py        (reads MQTT__* settings from .env)
"""

import asyncio

from fall_detector.inputs.mqtt_client import MQTTClient
from fall_detector.observability.logging_setup import configure_logging
from fall_detector.settings import load_settings


async def main() -> None:
    settings = load_settings().mqtt
    client = MQTTClient(
        settings.host,
        settings.port,
        settings.topic,
        settings.username,
        settings.password.get_secret_value() if settings.password else None,
    )
    listener = asyncio.create_task(client.run_forever())
    print(f"Listening on {settings.topic} (Ctrl+C to stop)...")
    try:
        while True:
            print("Received:", await client.messages.get())
    finally:
        listener.cancel()


if __name__ == "__main__":
    configure_logging("DEBUG")
    asyncio.run(main())
