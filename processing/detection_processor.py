import cv2
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import asyncio
import logging
import json

from telegram.error import TelegramError, RetryAfter, TimedOut, NetworkError
from fall.fall_detector import FallDetector
from comm.ami_trigger import AMITrigger
from comm.telegram_bot import TelegramBot
from database.database_manager import insert_fall_event
from utils.draw_utils import draw_person
from config.config import ALERT_COOLDOWN_MINUTES

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Limit concurrent Telegram requests
telegram_semaphore = asyncio.Semaphore(5)


class DetectionProcessor:
    def __init__(self, ami_trigger: AMITrigger, telegram_bot: Optional[TelegramBot]):
        self.fall_detectors: Dict[str, FallDetector] = {}
        self.last_alert_timestamps: Dict[str, datetime] = {}
        self.last_fall_timestamps: Dict[str, float] = {}
        self.entity_last_seen: Dict[str, datetime] = {}

        self.ami_trigger = ami_trigger
        self.telegram_bot = telegram_bot
        self.cooldown_minutes = ALERT_COOLDOWN_MINUTES

    async def handle_camera_data(self, frame: Optional[np.ndarray], person_id: int, box: list, landmarks: list):
        """Process camera frame, detect falls, and send alerts if needed."""
        entity_id = f"camera_person_{person_id}"
        self.entity_last_seen[entity_id] = datetime.now()
        detector = self._get_or_create_detector(entity_id)
        is_fall = detector.detect_fall(landmarks)

        if frame is not None and isinstance(frame, np.ndarray) and frame.size > 0:
            status = "fall" if is_fall else "normal"
            draw_person(frame, box, landmarks, entity_id, status)

        # Camera chỉ dùng cooldown (event_ts=None)
        if is_fall and self._can_alert(entity_id): 
            # Dùng timestamp hiện tại vì không có GPS/Device time
            fall_event = self._create_fall_event("camera", entity_id, latitude=0, longitude=0, has_gps_fix=False) 
            fall_id = await self._insert_fall_event_with_retry(fall_event)
            if fall_id is None:
                return

            alert_msg = f"⚠️ Fall detected by camera for {entity_id}. Event ID: {fall_id}"
            logger.info(alert_msg)
            await self._send_alerts(alert_msg, frame)
            self._update_last_alert(entity_id)

    async def handle_mqtt_data(self, mqtt_msg: Any, topic: str = None) -> None:
        """Process MQTT data from ESP32, validate, and handle fall alerts."""
        logger.info(f"[MQTT] 📥 Raw message on topic '{topic}': {mqtt_msg}")

        # Parse JSON
        if not isinstance(mqtt_msg, dict):
            try:
                mqtt_msg = json.loads(mqtt_msg)
                if not isinstance(mqtt_msg, dict):
                    logger.error(f"[MQTT] Invalid message format: expected dict, got {type(mqtt_msg)}")
                    return
            except (json.JSONDecodeError, TypeError):
                logger.error("[MQTT] Failed to parse JSON payload")
                return

        # Validate required fields
        device_id = mqtt_msg.get("device_id")
        fall_detected = mqtt_msg.get("fall_detected")
        # ✅ Lấy timestamp từ MQTT để deduplication
        event_ts = mqtt_msg.get("timestamp") 

        if not device_id or fall_detected is not True or not isinstance(event_ts, (int, float)):
            logger.debug(f"[MQTT] Skipping message: Required fields (device_id, fall_detected=True, timestamp) missing/invalid.")
            return

        latitude = mqtt_msg.get("latitude")
        longitude = mqtt_msg.get("longitude")
        has_gps_fix = mqtt_msg.get("has_gps_fix", False)
        
        # Validate GPS coordinates (giữ nguyên logic kiểm tra range)
        if latitude is not None and longitude is not None:
            if not (isinstance(latitude, (int, float)) and isinstance(longitude, (int, float))):
                logger.error(f"[MQTT] Invalid GPS: latitude={latitude}, longitude={longitude}")
                return
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                logger.error(f"[MQTT] GPS out of range: latitude={latitude}, longitude={longitude}")
                return
        if not isinstance(has_gps_fix, bool):
            has_gps_fix = False

        self.entity_last_seen[device_id] = datetime.now()
        logger.info(f"[MQTT] ✅ Parsed: device_id={device_id}, fall_detected={fall_detected}, ts={event_ts}")

        # ✅ DEDUP: Sử dụng timestamp của event_ts từ thiết bị để check lặp
        if self._can_alert(device_id, event_ts=event_ts):
            # Pass event_ts vào _create_fall_event để đảm bảo timestamp DB chính xác
            fall_event = self._create_fall_event("esp32", device_id, latitude, longitude, has_gps_fix, event_ts) 
            fall_id = await self._insert_fall_event_with_retry(fall_event)
            if fall_id is None:
                logger.error(f"[MQTT] Failed to insert fall event for device {device_id}")
                return

            gps_info = f"{latitude}, {longitude}" if has_gps_fix and latitude is not None else "Unknown"
            alert_msg = f"🚨 Fall detected by device {device_id} at GPS: {gps_info}. Event ID: {fall_id}"
            logger.info(alert_msg)
            await self._send_alerts(alert_msg, None)
            self._update_last_alert(device_id)
        else:
            logger.debug(f"[MQTT] Skipping alert for {device_id} (Deduplication or Cooldown active).")

    async def _send_alerts(self, msg: str, frame: Optional[np.ndarray] = None):
        """
        Centralized alert sending to AMI and Telegram.
        Sử dụng asyncio.create_task để gửi cảnh báo song song.
        """
        ami_task = asyncio.create_task(self._send_ami_alert(msg), name="ami_alert")
        telegram_task = asyncio.create_task(self._send_telegram_alert(msg, frame), name="telegram_alert")
        
        # Chờ cả hai hoàn thành, không để lỗi chặn nhau
        await asyncio.gather(ami_task, telegram_task, return_exceptions=True)

    async def _send_ami_alert(self, msg: str):
        """Helper to send AMI alert with error handling."""
        try:
            await self.ami_trigger.alert_devices(msg)
            logger.info("[ALERT] AMI alert sent successfully.")
        except Exception as e:
            logger.error(f"[ALERT] Failed AMI send: {e}")

    async def _send_telegram_alert(self, msg: str, frame: Optional[np.ndarray]):
        """Helper to send Telegram alert with safe retry logic."""
        try:
            await self._safe_send_telegram(frame, msg)
            logger.info("[ALERT] Telegram alert sent successfully.")
        except Exception as e:
            logger.error(f"[ALERT] Failed Telegram send: {e}")

    async def _safe_send_telegram(self, frame: Optional[np.ndarray], msg: str, retries: int = 3, delay: float = 2.0):
        """Safely send Telegram message/photo with retries and fallback."""
        if not self.telegram_bot:
            logger.warning("[TELEGRAM] Bot not initialized, skipping")
            return

        async with telegram_semaphore:
            for attempt in range(retries):
                try:
                    if self._is_valid_frame(frame):
                        frame = self._resize_and_compress_frame(frame)
                        await self.telegram_bot.send_photo(frame, msg)
                        return
                    await self.telegram_bot.send_message(msg)
                    return
                except (RetryAfter, TimedOut, NetworkError) as e:
                    logger.warning(f"[TELEGRAM] Network issue (attempt {attempt + 1}): {e}")
                    await asyncio.sleep(delay * (2 ** attempt))
                except TelegramError as e:
                    logger.error(f"[TELEGRAM] Error (attempt {attempt + 1}): {e}")
                    await asyncio.sleep(delay * (2 ** attempt))
                except Exception as e:
                    logger.error(f"[TELEGRAM] Unexpected error (attempt {attempt + 1}): {e}")
                    await asyncio.sleep(delay * (2 ** attempt))

            logger.warning("[TELEGRAM] All retries failed, sending text fallback")
            try:
                await self.telegram_bot.send_message(msg)
            except Exception as e:
                logger.error(f"[TELEGRAM] Fallback failed: {e}")

    def _is_valid_frame(self, frame: Optional[np.ndarray]) -> bool:
        """Check if frame is valid for sending."""
        return (
            isinstance(frame, np.ndarray)
            and frame.size > 0
            and frame.shape[0] >= 10
            and frame.shape[1] >= 10
        )

    def _resize_and_compress_frame(self, frame: np.ndarray) -> np.ndarray:
        """Resize and compress frame if too large."""
        if max(frame.shape[:2]) > 1080:
            scale = 1080 / max(frame.shape[:2])
            frame = cv2.resize(frame, None, fx=scale, fy=scale)
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 75]
        success, img_encoded = cv2.imencode(".jpg", frame, encode_param)
        if success:
            logger.debug(f"[TELEGRAM] Compressed size: {len(img_encoded) / (1024 * 1024):.2f} MB")
            return cv2.imdecode(img_encoded, cv2.IMREAD_COLOR)
        return frame

    def _create_fall_event(self, source: str, entity_id: str, latitude: float, longitude: float, has_gps_fix: bool, timestamp: Optional[float] = None) -> Dict[str, Any]:
        """Create a fall event dict."""
        return {
            "timestamp": timestamp if timestamp is not None else datetime.now().timestamp(),
            "source": source,
            "entity_id": entity_id,
            "fall_detected": True,
            "latitude": latitude,
            "longitude": longitude,
            "has_gps_fix": has_gps_fix,
        }

    async def _insert_fall_event_with_retry(self, event: Dict[str, Any], retries: int = 3) -> Optional[int]:
        """Insert fall event with retries in a thread to avoid blocking the event loop."""
        for attempt in range(retries):
            try:
                # Chạy blocking DB call trong thread pool
                last_id = await asyncio.to_thread(insert_fall_event, event)
                return last_id
            except Exception as e:
                logger.warning(f"[DB] Insert failed (attempt {attempt + 1}): {e}")
                # Exponential backoff
                await asyncio.sleep(1 * (2 ** attempt))
        logger.error("[DB] All insert retries failed")
        return None

    def _get_or_create_detector(self, entity_id: str) -> FallDetector:
        """Get or create FallDetector."""
        if entity_id not in self.fall_detectors:
            self.fall_detectors[entity_id] = FallDetector()
        return self.fall_detectors[entity_id]

    def _can_alert(self, entity_id: str, event_ts: Optional[float] = None) -> bool:
        """
        Check if alert cooldown has passed AND (cho nguồn MQTT) event timestamp is new.
        - event_ts=None: Camera/Sensor local (chỉ check cooldown).
        - event_ts=float: MQTT (check deduplication VÀ cooldown).
        """
        # 1. Deduplication check (chỉ áp dụng cho nguồn có timestamp)
        if event_ts is not None:
            last_event_ts = self.last_fall_timestamps.get(entity_id)
            if last_event_ts == event_ts:
                logger.debug(f"[DEDUP] Blocking alert for {entity_id}: Duplicate timestamp {event_ts}")
                return False  # Block duplicate event

            # Cập nhật last_fall_timestamps (vì đây là event mới)
            self.last_fall_timestamps[entity_id] = event_ts

        # 2. Cooldown check (áp dụng cho tất cả các nguồn)
        now = datetime.now()
        last_alert = self.last_alert_timestamps.get(entity_id)
        
        is_cooldown_expired = last_alert is None or (now - last_alert) > timedelta(minutes=self.cooldown_minutes)
        
        if not is_cooldown_expired:
            logger.debug(f"[COOLDOWN] Blocking alert for {entity_id}: Cooldown active.")
        
        return is_cooldown_expired

    def evict_stale_detectors(self, max_age_seconds: float = 30.0):
        """Remove state for entities not seen within max_age_seconds."""
        now = datetime.now()
        stale = [
            eid for eid, last in self.entity_last_seen.items()
            if (now - last).total_seconds() > max_age_seconds
        ]
        for eid in stale:
            self.fall_detectors.pop(eid, None)
            self.last_alert_timestamps.pop(eid, None)
            self.last_fall_timestamps.pop(eid, None)
            self.entity_last_seen.pop(eid, None)
            logger.debug(f"[EVICT] Evicted stale entity: {eid}")

    def _update_last_alert(self, entity_id: str):
        """Update last alert timestamp."""
        self.last_alert_timestamps[entity_id] = datetime.now()
