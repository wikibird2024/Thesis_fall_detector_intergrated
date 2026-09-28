import asyncio
from panoramisk.manager import Manager

# Configuration
MANAGER_CONFIG = {
    'host': '127.0.0.1',
    'port': 5038,
    'username': 'admin',  # You can change this to 'hx' if needed
    'secret': '123'
}

# List of target extensions
endpoints = ['6001', '6002', '6003']
message_text = "Alert: A fall has just been detected by the device!"

async def originate_call(manager, extension):
    """Make a call to the specified extension"""
    print(f"📞 Calling extension: {extension}")
    try:
        response = await manager.send_action({
            'Action': 'Originate',
            'Channel': f'PJSIP/{extension}',
            'Context': 'internal',
            'Exten': extension,
            'Priority': 1,
            'CallerID': f'FallAlert <{extension}>',
            'Async': 'true'
        })
        print(f"[{extension}] Call result: {response.get('Response')} - {response.get('Message', 'Call initiated')}")
    except Exception as e:
        print(f"[{extension}] ❌ Error making call: {e}")

async def send_message(manager, extension):
    """Send SMS message to the specified extension"""
    print(f"📨 Sending message to: {extension}")
    try:
        response = await manager.send_action({
            'Action': 'MessageSend',
            'To': f'pjsip:{extension}',
            'From': 'pjsip:server',  # Must match configuration in pjsip.conf
            'Body': message_text
        })
        print(f"[{extension}] SMS result: {response.get('Response')} - {response.get('Message')}")
    except Exception as e:
        print(f"[{extension}] ❌ Error sending message: {e}")

async def alert_extension(manager, extension):
    """Send both call and SMS to an extension"""
    print(f"🚨 Alerting extension {extension} via call and SMS")
    await asyncio.gather(
        originate_call(manager, extension),
        send_message(manager, extension)
    )

async def main():
    # Create manager instance
    manager = Manager(**MANAGER_CONFIG)
    
    try:
        # Connect to AMI
        print("🔌 Connecting to Asterisk AMI...")
        await manager.connect()
        print("✅ Connected successfully!")
        
        # Send alerts to all extensions simultaneously
        print(f"🚨 Sending fall alerts to {len(endpoints)} extensions...")
        await asyncio.gather(*[
            alert_extension(manager, ext) for ext in endpoints
        ])
        
        # Wait a bit to ensure all actions complete
        print("⏳ Waiting for actions to complete...")
        await asyncio.sleep(5)
        
    except Exception as e:
        print(f"❌ Error in main execution: {e}")
    
    finally:
        # Close the connection
        print("🔌 Closing AMI connection...")
        manager.close()
        print("✅ Connection closed")

if __name__ == '__main__':
    print("🚨 Fall Detection Alert System Starting...")
    asyncio.run(main())
