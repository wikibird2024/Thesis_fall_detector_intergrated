from panoramisk.manager import Manager
import asyncio

loop = asyncio.get_event_loop()

manager = Manager(
    loop=loop,
    host='127.0.0.1',
    port=5038,
    username='hx',
    secret='123'
)

async def originate(extension):
    response = await manager.send_action({
        'Action': 'Originate',
        'Channel': f'PJSIP/{extension}',
        'Context': 'internal',
        'Exten': extension,
        'Priority': 1,
        'CallerID': f'FallAlert <{extension}>',
        'Async': 'true'
    })
    print(f"Call to {extension}:", response)

async def main():
    await manager.connect()
    await asyncio.gather(
        originate('6001'),
        originate('6002'),
        # Add more if needed: originate('6003'), etc.
    )
    await asyncio.sleep(5)
    manager.close()

loop.run_until_complete(main())

