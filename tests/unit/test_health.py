"""Health and metrics endpoints."""

import pytest
from aiohttp.test_utils import TestClient, TestServer

from fall_detector.observability import metrics
from fall_detector.observability.health import create_health_app


@pytest.fixture
def status():
    return {"ready": True, "camera": {"enabled": False}}


@pytest.fixture
async def client(status):
    async with TestClient(TestServer(create_health_app(lambda: status))) as client:
        yield client


async def test_live_is_always_ok(client):
    response = await client.get("/health/live")
    assert response.status == 200


async def test_ready_returns_200_with_details_when_ready(client):
    response = await client.get("/health/ready")
    assert response.status == 200
    assert (await response.json())["camera"] == {"enabled": False}


async def test_ready_returns_503_when_not_ready(client, status):
    status["ready"] = False
    response = await client.get("/health/ready")
    assert response.status == 503


async def test_metrics_are_in_prometheus_format(client):
    metrics.FRAMES_PROCESSED.inc()
    response = await client.get("/metrics")
    body = await response.text()
    assert response.status == 200
    assert "fall_detector_frames_processed_total" in body
