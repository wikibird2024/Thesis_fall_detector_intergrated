
# get_chat_id.py
import os
import asyncio
from telegram import Bot
from dotenv import load_dotenv

# -----------------------------
# Load token từ file .env
# -----------------------------
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise ValueError("Bạn chưa đặt TELEGRAM_BOT_TOKEN trong file .env")

# -----------------------------
# Async function chính
# -----------------------------
async def main():
    bot = Bot(token=TOKEN)

    try:
        # Lấy tất cả updates chưa đọc (không chờ timeout dài)
        updates = await bot.get_updates(offset=-1)

        if not updates:
            print("Chưa có tin nhắn nào gửi tới bot. Hãy nhắn /start cho bot trước khi chạy script.")
            return

        latest_message = updates[-1].message
        chat_id = latest_message.chat.id
        username = latest_message.chat.username or "Không có username"

        print(f"Chat ID của bạn: {chat_id}")
        print(f"Username Telegram: {username}")

    except Exception as e:
        print("Lỗi khi lấy chat ID:", e)

    finally:
        # Đóng bot an toàn
        try:
            await bot.close()
        except:
            pass  # Nếu bị flood control thì bỏ qua

# -----------------------------
# Chạy script
# -----------------------------
if __name__ == "__main__":
    asyncio.run(main())
