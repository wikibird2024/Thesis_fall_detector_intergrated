
import os
from dotenv import load_dotenv
# Load environment variables from .env
load_dotenv()

# ==============================
# FallDetector thresholds
# ==============================
TORSO_ANGLE_THRESHOLD_VERTICAL: float = 60.0      # Maximum torso tilt (degrees) to consider upright
TORSO_ANGLE_THRESHOLD_HORIZONTAL: float = 45.0    # Maximum torso tilt (degrees) sideways to consider upright
VELOCITY_THRESHOLD: float = 0.5                    # Minimum torso velocity (units/frame) to detect falling
FALL_DURATION_THRESHOLD: int = 5                   # Consecutive frames exceeding fall criteria to confirm fall
FALL_STATE_DURATION_THRESHOLD: int = 5             # Frames lying down to confirm fall state
MIN_LANDMARK_CONFIDENCE: float = 0.5               # Minimum confidence for key landmarks (shoulders, hips)

# ==============================
# MQTT Configuration
# ==============================
MQTT_BROKER_HOST = "io.adafruit.com"
MQTT_BROKER_PORT = 1883
MQTT_USERNAME = os.getenv("MQTT_USERNAME")        # bí mật -> .env
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")        # bí mật -> .env
MQTT_TOPIC = "tranhao/feeds/fall_alert"
MQTT_KEEPALIVE = 60
ENABLE_MQTT = True

# ==============================
# Telegram Configuration
# ==============================
ENABLE_TELEGRAM = True
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # bí mật -> .env
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")      # bí mật -> .env

# ==============================
# Video Sources (centralized configuration)
# ==============================
def get_video_sources():
    """
    Load video sources based on priority:
    1. HTTP stream from environment variable (if set).
    2. External USB webcam (index 2).
    3. Laptop's default webcam (index 0).
    4. Alternative external webcam (index 1).
    """
    sources = []
    
    # Check for ESP32-CAM stream URL
    stream_url = os.getenv("VIDEO_STREAM_URL")
    if stream_url:
        sources.append(stream_url)
    
    # Add prioritized webcam indices
    sources.append(2)  # External webcam
    sources.append(0)  # Laptop's default webcam
    sources.append(1)  # Alternative external webcam fallback

    return sources

# ==============================
# Debug / Logging
# ==============================
ENABLE_DEBUG = True
LOG_LEVEL = "INFO"

# ==============================
# Skeleton Tracker
# ==============================
POSE_MODEL_COMPLEXITY = 1
POSE_MIN_DETECTION_CONFIDENCE = 0.5
POSE_MIN_TRACKING_CONFIDENCE = 0.5

# ==============================
# Human Detection
# ==============================
HUMAN_DETECTION_CONFIDENCE_THRESHOLD = 0.5
IOU_THRESHOLD = 0.7
FALL_DETECTION_THRESHOLD = 0.5

# ==============================
# Drawing / Visualization
# ==============================
BOUNDING_BOX_COLOR = (0, 255, 0)
BOUNDING_BOX_THICKNESS = 2
SKELETON_LINE_COLOR = (0, 0, 255)
SKELETON_LINE_THICKNESS = 2
SKELETON_POINT_COLOR = (255, 0, 0)
SKELETON_POINT_RADIUS = 5

# ==============================
# AMI / Asterisk Trigger
# ==============================
AMI_HOST = "127.0.0.1"
AMI_PORT = 5038
AMI_USERNAME = os.getenv("AMI_USERNAME")      # bí mật -> .env
AMI_SECRET = os.getenv("AMI_SECRET")          # bí mật -> .env
ENABLE_AMI = True

EXTENSIONS = ['6001', '6002', '6004']
ALERT_MESSAGE = "Fall detected! Please check immediately."
CALLER_ID = "FallAlertSystem <1000>"

# ==============================
# Optional AMI REST API
# ==============================
AMI_API_ENDPOINT = "http://your-ami-api-endpoint"
AMI_API_KEY = os.getenv("AMI_API_KEY")        # bí mật -> .env
