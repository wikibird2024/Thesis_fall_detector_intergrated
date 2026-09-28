"""Drawing, JPEG snapshots and the ESP32 MJPEG parser (no models needed)."""

import cv2
import numpy as np
import pytest

from builders import box, standing
from fall_detector.inputs import video_source
from fall_detector.inputs.video_source import ESP32StreamWrapper, find_and_connect_source
from fall_detector.vision.drawing import POSE_CONNECTIONS, draw_person, encode_jpeg, fall_snapshot

FRAME = np.zeros((480, 640, 3), dtype=np.uint8)


def test_draw_person_marks_the_frame():
    frame = FRAME.copy()
    draw_person(frame, box(100, 100, 200, 300), standing(), "camera_person_1", is_fall=True)
    assert frame.any()


def test_snapshot_does_not_change_original_frame():
    frame = FRAME.copy()
    jpeg = fall_snapshot(frame, box(100, 100, 200, 300), standing(), "p1")
    assert jpeg.startswith(b"\xff\xd8")
    assert not frame.any()


def test_large_frame_is_downscaled_before_encoding():
    jpeg = encode_jpeg(np.zeros((2160, 3840, 3), dtype=np.uint8))
    decoded = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    assert max(decoded.shape[:2]) == 1080


@pytest.mark.parametrize("bad", [None, np.zeros((5, 5, 3), dtype=np.uint8), "not a frame"])
def test_unusable_frame_gives_no_jpeg(bad):
    assert encode_jpeg(bad) is None


@pytest.mark.vision
def test_pose_connections_match_mediapipe():
    mp = pytest.importorskip("mediapipe")
    assert set(POSE_CONNECTIONS) == set(mp.solutions.pose.POSE_CONNECTIONS)


# ---------------------------------------------------------------- ESP32 MJPEG parsing


def jpeg_bytes(value: int) -> bytes:
    ok, buffer = cv2.imencode(".jpg", np.full((32, 32, 3), value, dtype=np.uint8))
    assert ok
    return buffer.tobytes()


def stream_without_network(monkeypatch, chunks: list[bytes]) -> ESP32StreamWrapper:
    """ESP32StreamWrapper whose HTTP response yields the given chunks."""

    def fake_connect(self):
        self._chunks = iter(chunks)
        self.buffer = b""
        self.last_frame_time = video_source.time.monotonic()
        return True

    monkeypatch.setattr(ESP32StreamWrapper, "connect", fake_connect)
    return ESP32StreamWrapper("http://192.168.1.50:81/stream")


def test_frame_split_over_many_chunks_is_read_in_one_call(monkeypatch):
    # Regression: read() used to consume one 8 KB chunk per call and report
    # "no frame" for the rest, so the caller slept between chunks (~1 fps).
    data = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg_bytes(200) + b"\r\n"
    chunks = [data[i : i + 100] for i in range(0, len(data), 100)]
    stream = stream_without_network(monkeypatch, chunks)

    ok, frame = stream.read()
    assert ok and frame.shape == (32, 32, 3)


def test_two_frames_in_one_chunk_are_both_returned(monkeypatch):
    stream = stream_without_network(monkeypatch, [jpeg_bytes(10) + jpeg_bytes(250)])
    first, second = stream.read(), stream.read()
    assert first[0] and second[0]
    assert first[1].mean() < 50 < second[1].mean()


def test_end_of_stream_returns_no_frame(monkeypatch):
    stream = stream_without_network(monkeypatch, [])
    assert stream.read() == (False, None)


def test_non_http_url_is_rejected():
    with pytest.raises(ValueError):
        ESP32StreamWrapper("rtsp://camera/stream")


def test_no_working_source_returns_none(monkeypatch):
    class ClosedCapture:
        def __init__(self, source):
            pass

        def isOpened(self):
            return False

        def release(self):
            pass

    monkeypatch.setattr(video_source.cv2, "VideoCapture", ClosedCapture)
    assert find_and_connect_source([0, 1]) is None
