import asyncio
from panoramisk.manager import Manager

# Establish AMI connection
manager = Manager(
    host='127.0.0.1',
    port=5038,
    username='admin',
    secret='123'
)

# List of target extensions
endpoints = ['6001', '6002', '6003']
message_text = "Alert: A fall has just been detected by the device!"

async def send_message(to_ext):
    print(f"📨 Sending message to: {to_ext}")
    try:
        response = await manager.send_action({
            'Action': 'MessageSend',
            'To': f'pjsip:{to_ext}',
            'From': 'pjsip:server',  # Must match configuration in pjsip.conf
            'Body': message_text
        })

        # The response is a dictionary (not a list), so print directly
        print(f"[{to_ext}] Send result: {response.get('Response')} - {response.get('Message')}")

    except Exception as e:
        print(f"[{to_ext}] ❌ Error sending message: {e}")

async def main():
    await manager.connect()

    # Send messages to each extension
    for ext in endpoints:
        await send_message(ext)

    # DO NOT use await here, since .close() is not async
    manager.close()

if __name__ == '__main__':
    asyncio.run(main())

