import cv2
import asyncio
from datetime import datetime
import json
from typing import Dict, Any, Optional
import time
import os
import logging

# Import application modules
from detection.human_detector import HumanDetector
from detection.skeleton_tracker import SkeletonTracker
from detection.person_tracker import PersonTracker
from processing.detection_processor import DetectionProcessor
from comm.mqtt_client import MQTTClient
from comm.ami_trigger import AMITrigger
from comm.telegram_bot import TelegramBot
from utils.draw_utils import draw_bounding_box, draw_skeleton
from database.database_manager import create_table
from utils.video_utils import find_and_connect_source
# Thêm nhập hàm cấu hình nguồn video
from config.config import get_video_sources

# Import all configuration variables
from config.config import (
    MQTT_BROKER_HOST, MQTT_BROKER_PORT, MQTT_TOPIC, MQTT_USERNAME, MQTT_PASSWORD, ENABLE_MQTT,
    AMI_HOST, AMI_PORT, AMI_USERNAME, AMI_SECRET, ENABLE_AMI,
    HUMAN_DETECTION_CONFIDENCE_THRESHOLD, IOU_THRESHOLD, POSE_MODEL_COMPLEXITY, POSE_MIN_DETECTION_CONFIDENCE,
    POSE_MIN_TRACKING_CONFIDENCE, ENABLE_TELEGRAM, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
)

# Setup logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("fall_system")


async def camera_processing_loop(cap, human_detector, skeleton_tracker, person_tracker, detection_processor):
    """
    Camera processing loop supporting multiple sources in priority order.
    `cap` can be a cv2.VideoCapture or ESP32StreamWrapper.
    """
    if cap is None:
        logger.error("[CAMERA] No working video source found, exiting camera loop")
        return

    try:
        frame_count = 0
        while True:
            # Async-safe read
            if hasattr(cap, "read"):
                # ESP32StreamWrapper or cv2.VideoCapture
                ret, frame = await asyncio.to_thread(cap.read)
            else:
                logger.error("[CAMERA] Invalid video source object")
                break

            if not ret or frame is None:
                # REFACTOR: Tăng thời gian chờ lên (từ 0.05s lên 0.3s)
                # Điều này giúp giảm spam log "Failed to read frame" khi camera mất kết nối tạm thời.
                logger.warning("[CAMERA] Failed to read frame, sleeping 0.3s...")
                await asyncio.sleep(0.3)
                continue

            # Detect humans
            detected_boxes = human_detector.detect_humans(frame)
            tracked_people = person_tracker.update(detected_boxes)

            # Track skeletons and handle detection
            for person_id, box in tracked_people:
                landmarks = skeleton_tracker.track_from_box(frame, box)
                await detection_processor.handle_camera_data(frame, person_id, box, landmarks)

            # Optional: display frame
            cv2.imshow("Fall Detection", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                logger.info("[CAMERA] User pressed 'q', stopping camera...")
                break

            frame_count += 1
            if frame_count % 100 == 0:
                logger.info(f"[CAMERA] Processed {frame_count} frames")

            # Tối ưu: Dùng sleep ngắn hơn khi đọc thành công để tăng FPS/giảm latency, 
            # nhưng vẫn nhường quyền kiểm soát cho event loop.
            await asyncio.sleep(0.001)

    except asyncio.CancelledError:
        logger.info("[CAMERA] Camera processing task cancelled")
    except Exception as e:
        logger.exception(f"[CAMERA] Error in camera processing: {e}")
    finally:
        if cap:
            logger.info("[CAMERA] Releasing camera...")
            if hasattr(cap, "release"):
                await asyncio.to_thread(cap.release)
            cv2.destroyAllWindows()


async def heartbeat_loop():
    """Heartbeat loop to keep program alive and show it's working."""
    try:
        while True:
            await asyncio.sleep(60)
            logger.info("[SYSTEM] Heartbeat - all tasks running")
    except asyncio.CancelledError:
        logger.info("[SYSTEM] Heartbeat cancelled")


async def mqtt_processor_loop(mqtt_client: MQTTClient, detection_processor: DetectionProcessor):
    """Background task to process MQTT messages from the queue."""
    logger.info("[MQTT] Processor started")
    try:
        while mqtt_client.is_running():
            try:
                mqtt_msg = await mqtt_client.get_message(timeout=1.0)
                logger.info(f"[MQTT] Processing message: {mqtt_msg}")
                await detection_processor.handle_mqtt_data(mqtt_msg)
            except asyncio.TimeoutError:
                pass
    except asyncio.CancelledError:
        logger.info("[MQTT] Processor task cancelled.")
    except Exception as e:
        logger.exception(f"[MQTT] Processor error: {e}")
        raise


async def cleanup_resources(skeleton_tracker, ami_trigger):
    """Final cleanup of resources that need explicit closing."""
    logger.info("[SYSTEM] Final cleanup...")

    if skeleton_tracker:
        try:
            skeleton_tracker.close()
            logger.info("[SKELETON] Skeleton tracker closed")
        except Exception as e:
            logger.warning(f"[SKELETON] Error closing: {e}")

    if ami_trigger and getattr(ami_trigger, "is_connected", False):
        try:
            await ami_trigger.close()
            logger.info("[AMI] AMI connection closed")
        except Exception as e:
            logger.warning(f"[AMI] Error closing: {e}")

    logger.info("[SYSTEM] Cleanup completed")


async def main():
    """Main async function to run the fall detection system."""

    mqtt_client = None
    skeleton_tracker = None
    ami_trigger = None
    tasks = []

    try:
        logger.info("[SYSTEM] Initializing modules...")
        human_detector = HumanDetector(
            conf_threshold=HUMAN_DETECTION_CONFIDENCE_THRESHOLD,
            iou_threshold=IOU_THRESHOLD
        )
        skeleton_tracker = SkeletonTracker(
            model_complexity=POSE_MODEL_COMPLEXITY,
            min_detection_confidence=POSE_MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=POSE_MIN_TRACKING_CONFIDENCE
        )
        person_tracker = PersonTracker(iou_threshold=IOU_THRESHOLD)
        ami_trigger = AMITrigger(
            host=AMI_HOST, port=AMI_PORT, username=AMI_USERNAME, secret=AMI_SECRET
        )

        telegram_bot = None
        if ENABLE_TELEGRAM:
            telegram_bot = TelegramBot(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
            logger.info("[TELEGRAM] Bot initialized.")

        detection_processor = DetectionProcessor(ami_trigger, telegram_bot)

        # Initialize the database
        create_table()
        logger.info("[DB] Database and table created successfully.")

        # Start MQTT tasks
        if ENABLE_MQTT:
            try:
                mqtt_client = MQTTClient(
                    broker=MQTT_BROKER_HOST,
                    port=MQTT_BROKER_PORT,
                    topic=MQTT_TOPIC,
                    username=MQTT_USERNAME,
                    password=MQTT_PASSWORD,
                )
                tasks.append(asyncio.create_task(mqtt_client.run_forever(), name="mqtt_listener"))
                logger.info("[MQTT] MQTT listener task created")
            except Exception as e:
                logger.warning(f"[MQTT] Could not start MQTT: {e}")
                mqtt_client = None
        else:
            logger.info("[MQTT] Disabled by configuration.")

        # Wait for MQTT connection
        if mqtt_client:
            try:
                await asyncio.wait_for(mqtt_client.connected_event.wait(), timeout=10)
                logger.info("[MQTT] MQTT client connected.")
                tasks.append(asyncio.create_task(mqtt_processor_loop(mqtt_client, detection_processor), name="mqtt_processor"))
                logger.info("[MQTT] MQTT processor task created")
            except asyncio.TimeoutError:
                logger.warning("[MQTT] Timeout waiting for MQTT connection. Proceeding without MQTT processing.")

        # Connect AMI trigger
        if ENABLE_AMI:
            try:
                await ami_trigger.connect()
            except Exception as e:
                logger.warning(f"[AMI] Error connecting to AMI: {e}. Proceeding without AMI functionality.")
                ami_trigger.is_connected = False
        else:
            logger.info("[AMI] AMI functionality is disabled.")
            ami_trigger.is_connected = False

        # Get camera source
        source_priority_list = get_video_sources()
        cap = find_and_connect_source(source_priority_list)

        # Start camera processing task
        camera_task = asyncio.create_task(
            camera_processing_loop(cap, human_detector, skeleton_tracker, person_tracker, detection_processor),
            name="camera_processing"
        )
        tasks.append(camera_task)

        # Start heartbeat task
        heartbeat_task = asyncio.create_task(heartbeat_loop(), name="heartbeat")
        tasks.append(heartbeat_task)

        logger.info(f"[SYSTEM] Starting {len(tasks)} concurrent tasks...")
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        for task in done:
            if task.exception():
                logger.error(f"[SYSTEM] Task {task.get_name()} failed: {task.exception()}")
            else:
                logger.info(f"[SYSTEM] Task {task.get_name()} completed normally.")

        # Cancel remaining tasks
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.wait(pending, timeout=5.0)

    except KeyboardInterrupt:
        logger.info("[SYSTEM] Keyboard interrupt received")
    except Exception as e:
        logger.exception(f"[SYSTEM] Unexpected error: {e}")
    finally:
        await cleanup_resources(skeleton_tracker, ami_trigger)


if __name__ == "__main__":
    logger.info("[SYSTEM] Starting Fall Detection System...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[SYSTEM] Program interrupted by user")
    finally:
        logger.info("[SYSTEM] Goodbye!")
