
# test_mqtt.py
import asyncio
from comm.mqtt_client import MQTTClient  # import class bạn đã viết


async def main():
    # Thay đổi theo broker thật của bạn
    broker = "io.adafruit.com"
    port = 1883
    topic = "tranhao/feeds/json_data"
    username = "tranhao"      # nếu broker yêu cầu
    password = ""  # nếu broker yêu cầu

    mqtt_client = MQTTClient(
        broker=broker,
        port=port,
        topic=topic,
        username=username,
        password=password,
        qos=0,
    )

    # chạy client trong background
    asyncio.create_task(mqtt_client.run_forever())

    print("[TEST] 🚀 MQTT client started, waiting for messages...")

    # liên tục lấy message từ queue
    while True:
        msg = await mqtt_client.get_message()
        print(f"[TEST] ✅ Received MQTT message: {msg}")


if __name__ == "__main__":
    asyncio.run(main())
