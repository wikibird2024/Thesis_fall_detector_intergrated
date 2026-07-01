import asyncio
from panoramisk.manager import Manager

# === AMI Configuration ===
AMI_HOST = '127.0.0.1'
AMI_PORT = 5038
AMI_USERNAME = 'hx'
AMI_SECRET = '123'

# === Fall Alert Settings ===
EXTENSIONS = ['6001', '6002', '6003']
ALERT_MESSAGE = "⚠️ Alert: A fall has just been detected by the device!"
CALLER_ID = "FallAlert"

# === AMI Manager Instance ===
manager = Manager(
    host=AMI_HOST,
    port=AMI_PORT,
    username=AMI_USERNAME,
    secret=AMI_SECRET
)

# === Send Call ===
async def originate_call(ext: str):
    try:
        response = await manager.send_action({
            'Action': 'Originate',
            'Channel': f'PJSIP/{ext}',
            'Context': 'internal',  # Match your dialplan context
            'Exten': ext,
            'Priority': 1,
            'CallerID': f'{CALLER_ID} <{ext}>',
            'Async': 'true'
        })
        print(f"[📞 CALL] → {ext} | Status: {response.get('Response')} - {response.get('Message')}")
    except Exception as e:
        print(f"[📞 CALL] → {ext} | ❌ Error: {e}")

# === Send Message ===
async def send_message(ext: str):
    try:
        response = await manager.send_action({
            'Action': 'MessageSend',
            'To': f'pjsip:{ext}',
            'From': 'pjsip:server',  # Must match extensions.conf
            'Body': ALERT_MESSAGE
        })
        print(f"[📨 SMS] → {ext} | Status: {response.get('Response')} - {response.get('Message')}")
    except Exception as e:
        print(f"[📨 SMS] → {ext} | ❌ Error: {e}")

# === Handle One Extension (Both Tasks in Parallel) ===
async def handle_extension(ext: str):
    await asyncio.gather(
        originate_call(ext),
        send_message(ext)
    )

# === Entry Point ===
async def main():
    await manager.connect()

    # Run all extension handlers in parallel
    await asyncio.gather(*(handle_extension(ext) for ext in EXTENSIONS))

    await asyncio.sleep(2)  # Ensure all responses are received
    manager.close()

if __name__ == '__main__':
    asyncio.run(main())

