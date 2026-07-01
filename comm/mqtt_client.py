import asyncio
import json
import logging
from typing import Dict, Any, Optional
import aiomqtt

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MQTTClient:
    """
    Asynchronous MQTT client for connecting to a broker and handling messages.
    Parses incoming MQTT payloads as JSON and normalizes them.
    """
    def __init__(
        self,
        broker: str = "localhost",
        port: int = 1883,
        topic: str = "fall/detection",
        username: Optional[str] = None,
        password: Optional[str] = None,
        qos: int = 0,
        max_queue_size: int = 1000,
        max_retries: int = 10,
        retry_delay: int = 5
    ):
        self.broker = broker
        self.port = port
        self.topic = topic
        self.username = username
        self.password = password
        self.qos = qos
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.message_queue = asyncio.Queue(maxsize=max_queue_size)
        self.connected_event = asyncio.Event()
        self._running = True
        self._retry_count = 0

    async def run_forever(self):
        """
        Main loop: connects to the broker, subscribes to the topic,
        and processes incoming messages. It includes an automatic reconnect
        mechanism on failure.
        """
        logger.info(f"[MQTT] Starting connection to {self.broker}:{self.port}")
        logger.info(f"[MQTT] Topic: {self.topic}")
        logger.info(f"[MQTT] Username: {self.username}")
        logger.info(f"[MQTT] Password provided: {'Yes' if self.password else 'No'}")
        
        while self._running and self._retry_count < self.max_retries:
            try:
                logger.info(f"[MQTT] Connection attempt {self._retry_count + 1}/{self.max_retries}")
                
                async with aiomqtt.Client(
                    hostname=self.broker,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                ) as client:
                    logger.info(f"[MQTT] ✅ Connected to {self.broker}:{self.port}")
                    self.connected_event.set()
                    
                    await client.subscribe(self.topic, qos=self.qos)
                    logger.info(f"[MQTT] ✅ Subscribed to {self.topic} (QoS={self.qos})")
                    
                    # Reset retry count on successful connection
                    self._retry_count = 0
                    
                    async for message in client.messages:
                        if not self._running:
                            break
                        await self._process_message(message)
            
            except aiomqtt.MqttError as e:
                self.connected_event.clear()
                self._retry_count += 1
                logger.error(f"[MQTT] ❌ MQTT error (attempt {self._retry_count}/{self.max_retries}): {e}")
                if self._retry_count < self.max_retries:
                    logger.info(f"[MQTT] ⏳ Retrying in {self.retry_delay}s...")
                    await asyncio.sleep(self.retry_delay)
                else:
                    logger.error("[MQTT] ❌ Max retries reached, stopping client.")
                    self._running = False

            except asyncio.CancelledError:
                logger.info("[MQTT] 🛑 MQTT client task cancelled.")
                self._running = False
                break
                
            except Exception as e:
                self.connected_event.clear()
                self._retry_count += 1
                logger.error(f"[MQTT] ❌ Unexpected error (attempt {self._retry_count}/{self.max_retries}): {e}", exc_info=True)
                if self._retry_count < self.max_retries:
                    logger.info(f"[MQTT] ⏳ Retrying in {self.retry_delay}s...")
                    await asyncio.sleep(self.retry_delay)
                else:
                    logger.error("[MQTT] ❌ Max retries reached, stopping client.")
                    self._running = False

        logger.info("[MQTT] 🏁 MQTT client loop ended")

    async def stop(self):
        """Stop the MQTT client gracefully."""
        logger.info("[MQTT] 🛑 Stopping MQTT client...")
        self._running = False

    async def _process_message(self, message: aiomqtt.Message):
        """Processes an individual MQTT message, decodes, and queues it."""
        try:
            raw_payload = message.payload.decode(errors="ignore")
            logger.info(f"[MQTT] 📨 Raw message on {message.topic}: {raw_payload}")
            
            try:
                data = json.loads(raw_payload)
                normalized = self._normalize_data(data)
                logger.info(f"[MQTT] ✅ Parsed and normalized: {normalized}")
                
                try:
                    await asyncio.wait_for(
                        self.message_queue.put(normalized),
                        timeout=1.0
                    )
                    logger.info(f"[MQTT] 📥 Queued message successfully")
                except asyncio.TimeoutError:
                    logger.warning("[MQTT] ⚠️ Message queue full, dropping message.")
                    
            except json.JSONDecodeError as e:
                logger.warning(f"[MQTT] ⚠️ Invalid JSON payload: {raw_payload} - Error: {e}")
            except Exception as e:
                logger.error(f"[MQTT] ❌ Error parsing/queuing message: {e}", exc_info=True)
                
        except Exception as e:
            logger.error(f"[MQTT] ❌ Error processing message: {e}", exc_info=True)

    def _normalize_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize incoming data to standard format."""
        try:
            normalized = {
                "device_id": data.get("device_id", "unknown"),
                "fall_detected": self._to_bool(data.get("fall_detected", False)),
                "latitude": self._to_float(data.get("latitude")),
                "longitude": self._to_float(data.get("longitude")),
                "has_gps_fix": self._to_bool(data.get("has_gps_fix", False)),
                "timestamp": data.get("timestamp"),
                "raw_data": data  # Keep original for debugging
            }
            return normalized
        except Exception as e:
            logger.error(f"[MQTT] ❌ Error normalizing data: {e}", exc_info=True)
            # Return minimal normalized structure
            return {
                "device_id": "unknown",
                "fall_detected": False,
                "latitude": 0.0,
                "longitude": 0.0,
                "has_gps_fix": False,
                "timestamp": None,
                "raw_data": data
            }

    async def get_message(self, timeout: Optional[float] = None) -> Dict[str, Any]:
        """
        Retrieves a message from the internal queue.
        Waits for the client to be connected before trying to get a message.
        """
        logger.debug("[MQTT] 🔍 Waiting for connection before getting message...")
        await self.connected_event.wait()
        logger.debug("[MQTT] 🔍 Connection ready, getting message from queue...")
        
        if timeout is not None:
            return await asyncio.wait_for(self.message_queue.get(), timeout=timeout)
        return await self.message_queue.get()

    def get_queue_size(self) -> int:
        """Returns the current size of the message queue."""
        return self.message_queue.qsize()

    def is_running(self) -> bool:
        """Checks if the client is set to run."""
        return self._running

    def is_connected(self) -> bool:
        """Checks if the client is connected."""
        return self.connected_event.is_set()

    @staticmethod
    def _to_float(value) -> float:
        """Converts a value to float with a safe fallback."""
        if value is None:
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError, OverflowError):
            return 0.0

    @staticmethod
    def _to_bool(value) -> bool:
        """Converts a value to boolean with smart parsing."""
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower().strip() in ("true", "1", "yes", "y", "on")
        try:
            return bool(int(value))
        except (ValueError, TypeError):
            return bool(value)
