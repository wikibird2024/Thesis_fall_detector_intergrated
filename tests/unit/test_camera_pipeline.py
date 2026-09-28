"""CameraPipeline: frame loop, reconnect, decisions per person."""

import asyncio

from builders import box, lying, standing
from fakes import FakeAnalyzer, FakeVideoSource, RecordingSink, wait_until
from fall_detector.fall.fall_detector import FallThresholds
from fall_detector.processing.camera_pipeline import CameraPipeline
from fall_detector.processing.detection_processor import DetectionProcessor
from fall_detector.vision.analyzer import TrackedPerson


def make_pipeline(sources, analyzer, sink=None, **kwargs):
    sink = sink or RecordingSink()
    processor = DetectionProcessor(sink, thresholds=FallThresholds(lying_frames=3))
    queue = list(sources)
    pipeline = CameraPipeline(
        lambda: queue.pop(0) if queue else None, analyzer, processor, reconnect_delay_s=0.001, **kwargs
    )
    return pipeline, sink


async def run_until(pipeline, condition):
    task = asyncio.create_task(pipeline.run())
    try:
        await wait_until(condition)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_person_lying_for_three_frames_raises_one_alert():
    person = lambda landmarks: [TrackedPerson(4, box(10, 10, 100, 200), landmarks)]  # noqa: E731
    # Frame 2 (standing -> lying) moves the torso, so it counts as "falling", not "lying";
    # the lying count then needs 3 more frames.
    frames = [person(standing())] + [person(lying())] * 4
    pipeline, sink = make_pipeline([FakeVideoSource(frame_count=5)], FakeAnalyzer(frames))

    await run_until(pipeline, lambda: pipeline.frames_processed == 5)

    assert [e.entity_id for e in sink.events] == ["camera_person_4"]
    assert sink.images[0] is not None


async def test_lost_source_is_released_and_reopened():
    first, second = FakeVideoSource(frame_count=2), FakeVideoSource(frame_count=10_000)
    pipeline, _ = make_pipeline([first, second], FakeAnalyzer(), max_failed_reads=2)

    await run_until(pipeline, lambda: pipeline.frames_processed >= 5 and pipeline.is_connected)

    assert first.released
    # After the task is cancelled the current source is released too.
    assert second.released and not pipeline.is_connected


async def test_no_source_available_keeps_trying():
    attempts = []

    def open_source():
        attempts.append(1)
        return None

    processor = DetectionProcessor(RecordingSink())
    pipeline = CameraPipeline(open_source, FakeAnalyzer(), processor, reconnect_delay_s=0.001)
    await run_until(pipeline, lambda: len(attempts) >= 3)
    assert not pipeline.is_connected
