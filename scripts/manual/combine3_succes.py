import asyncio
from panoramisk.manager import Manager

# === AMI Configuration (Cần chính xác) ===
AMI_HOST = '127.0.0.1'
AMI_PORT = 5038
AMI_USERNAME = 'hx'
AMI_SECRET = '123'

# === Fall Alert Settings ===
# 🔑 ĐÃ THÊM 6004 VÀO DANH SÁCH CẦN TEST
EXTENSIONS = ['6001', '6002', '6003', '6004'] 
ALERT_MESSAGE = "⚠️ Cảnh báo: Phát hiện ngã tại vị trí hiện tại!"
CALLER_ID = "FallAlert"

# === AMI Manager Instance ===
manager = Manager(
    host=AMI_HOST,
    port=AMI_PORT,
    username=AMI_USERNAME,
    secret=AMI_SECRET
)

# === Send Call (Trỏ đến 9999 và Timeout 20s) ===
async def originate_call(ext: str):
    """
    Tạo cuộc gọi cảnh báo giả 20 giây.
    Trỏ đến Exten 9999 (điểm thoát) và dùng Timeout 20000ms để kiểm soát thời gian đổ chuông.
    """
    try:
        response = await manager.send_action({
            'Action': 'Originate',
            'Channel': f'PJSIP/{ext}',
            'Context': 'internal',
            'Exten': '9999',         # Exten 9999 là điểm thoát sạch trong extensions.ael
            'Priority': 1,
            'CallerID': f'{CALLER_ID} <{ext}>',
            'Timeout': 20000,        # Đặt Timeout 20 giây (20000ms)
            'Async': 'true'
        })
        print(f"[📞 CALL] → {ext} | Status: {response.get('Response')} - {response.get('Message')}")
    except Exception as e:
        print(f"[📞 CALL] → {ext} | ❌ Error: {e}")

# === Send Message (Khắc phục lỗi cú pháp URI) ===
async def send_message(ext: str):
    """Gửi tin nhắn SIP với URI hợp lệ."""
    try:
        response = await manager.send_action({
            'Action': 'MessageSend',
            'To': f'pjsip:{ext}',
            # URI SIP hợp lệ, khớp với logic đã sửa trong extensions.ael
            'From': 'sip:alert-system@127.0.0.1', 
            'Body': ALERT_MESSAGE
        })
        print(f"[📨 SMS] → {ext} | Status: {response.get('Response')} - {response.get('Message')}")
    except Exception as e:
        print(f"[📨 SMS] → {ext} | ❌ Error: {e}")

# === Handle One Extension (Both Tasks in Parallel) ===
async def handle_extension(ext: str):
    print(f"--- Kích hoạt cảnh báo cho {ext} ---")
    await asyncio.gather(
        originate_call(ext),
        send_message(ext)
    )

# === Entry Point ===
async def main():
    await manager.connect()
    print("AMI Connected. Sending alerts...")

    # Chạy đồng thời cảnh báo cho tất cả 4 Extension
    await asyncio.gather(*(handle_extension(ext) for ext in EXTENSIONS))

    await asyncio.sleep(2)
    manager.close()
    print("Alerts sent. AMI Disconnected.")

if __name__ == '__main__':
    asyncio.run(main())
