
import io
import cv2
import numpy as np
import asyncio
from telegram import Bot
from telegram.error import TelegramError, RetryAfter, TimedOut, NetworkError

class TelegramBot:
    """
    Async Telegram bot wrapper (v22+) for sending messages and photos.
    Minimal, robust, retry-safe.
    """

    def __init__(self, token: str, chat_id: str, send_test_message: bool = True):
        self.bot = Bot(token=token)
        self.chat_id = chat_id

        if send_test_message:
            asyncio.create_task(self._send_test_message())

    async def _send_test_message(self):
        try:
            await self.send_message("✅ Telegram bot initialized successfully.")
            print("[TELEGRAM] Test message sent successfully.")
        except Exception as e:
            print(f"[TELEGRAM] ⚠️ Test message failed: {e}")

    async def send_message(self, text: str, retries: int = 3, delay: float = 1.0):
        for attempt in range(retries):
            try:
                await self.bot.send_message(chat_id=self.chat_id, text=text)
                return
            except (RetryAfter, TimedOut, NetworkError) as e:
                print(f"[TELEGRAM] ⚠️ Attempt {attempt+1} failed: {e}, retrying...")
                await asyncio.sleep(delay)
            except TelegramError as e:
                print(f"[TELEGRAM] ❌ TelegramError: {e}")
                return
            except Exception as e:
                print(f"[TELEGRAM] ❌ Unexpected error: {e}")
                return

    async def send_photo(self, frame: np.ndarray, caption: str = "", retries: int = 3, delay: float = 1.0):
        if not isinstance(frame, np.ndarray) or frame.size == 0:
            print("[TELEGRAM] ⚠️ Frame invalid or empty, sending text only")
            await self.send_message(caption)
            return

        frame_safe = self._prepare_frame(frame)
        success, img_encoded = cv2.imencode(".jpg", frame_safe)
        if not success:
            print("[TELEGRAM] ⚠️ Failed to encode image, sending text only")
            await self.send_message(caption)
            return

        photo_bytes = io.BytesIO(img_encoded.tobytes())
        photo_bytes.name = "image.jpg"
        photo_bytes.seek(0)

        for attempt in range(retries):
            try:
                await self.bot.send_photo(chat_id=self.chat_id, photo=photo_bytes, caption=caption)
                photo_bytes.close()
                return
            except (RetryAfter, TimedOut, NetworkError) as e:
                print(f"[TELEGRAM] ⚠️ Attempt {attempt+1} failed: {e}, retrying...")
                await asyncio.sleep(delay)
            except TelegramError as e:
                print(f"[TELEGRAM] ❌ TelegramError: {e}")
                break
            except Exception as e:
                print(f"[TELEGRAM] ❌ Unexpected error: {e}")
                break

        # fallback
        photo_bytes.close()
        await self.send_message(caption)

    @staticmethod
    def _prepare_frame(frame: np.ndarray) -> np.ndarray:
        """Ensure frame is uint8, 3-channel BGR."""
        if frame.dtype != np.uint8:
            frame_safe = cv2.convertScaleAbs(frame)
        else:
            frame_safe = frame.copy()

        if frame_safe.ndim == 2:  # grayscale
            frame_safe = cv2.cvtColor(frame_safe, cv2.COLOR_GRAY2BGR)
        elif frame_safe.ndim == 3 and frame_safe.shape[2] == 4:  # BGRA
            frame_safe = cv2.cvtColor(frame_safe, cv2.COLOR_BGRA2BGR)

        return frame_safe
