"""Small HTTP server for operations.

    GET /health/live   200 while the process runs (Docker/Kubernetes "is it alive?")
    GET /health/ready  200 if the system can detect AND alert, else 503, with JSON details
    GET /metrics       Prometheus metrics (see metrics.py)

Live vs ready: a live process may still be useless (camera unplugged, broker
down). An orchestrator restarts on failed liveness, and alerts on failed readiness.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from aiohttp import web
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

logger = logging.getLogger(__name__)

StatusProvider = Callable[[], dict[str, Any]]


def create_health_app(status: StatusProvider) -> web.Application:
    async def live(_: web.Request) -> web.Response:
        return web.json_response({"status": "alive"})

    async def ready(_: web.Request) -> web.Response:
        snapshot = status()
        return web.json_response(snapshot, status=200 if snapshot.get("ready") else 503)

    async def metrics(_: web.Request) -> web.Response:
        response = web.Response(body=generate_latest())
        response.headers["Content-Type"] = CONTENT_TYPE_LATEST
        return response

    app = web.Application()
    app.router.add_get("/health/live", live)
    app.router.add_get("/health/ready", ready)
    app.router.add_get("/metrics", metrics)
    return app


class HealthServer:
    def __init__(self, status: StatusProvider, host: str, port: int) -> None:
        self._app = create_health_app(status)
        self.host = host
        self.port = port
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        self._runner = web.AppRunner(self._app, access_log=None)
        await self._runner.setup()
        await web.TCPSite(self._runner, self.host, self.port).start()
        logger.info("Health endpoints on http://%s:%d/health/ready and /metrics", self.host, self.port)

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
