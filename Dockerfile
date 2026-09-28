# syntax=docker/dockerfile:1.6
# Multi-stage build: compilers and caches stay in the "build" stage,
# the final image only has what is needed to run.
#
#   docker build -t fall-detector .
#   docker run --env-file .env -p 8080:8080 fall-detector

ARG PYTHON_VERSION=3.10

# ---------------------------------------------------------------- base
FROM python:${PYTHON_VERSION}-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
# libGL/glib: needed by the OpenCV builds that MediaPipe and Ultralytics install.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------- build
FROM base AS build
WORKDIR /build
# Dependencies first: this layer is cached until the lock file changes.
COPY requirements.lock.txt .
RUN pip install --prefix=/install -r requirements.lock.txt
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --prefix=/install --no-deps .

# ---------------------------------------------------------------- runtime
FROM base AS runtime
COPY --from=build /install /usr/local

# YOLO weights are not in git. Pinned by checksum so a changed file fails the build.
ADD --checksum=sha256:31e20dde3def09e2cf938c7be6fe23d9150bbbe503982af13345706515f2ef95 \
    https://github.com/ultralytics/assets/releases/download/v8.1.0/yolov8n.pt /app/models/yolov8n.pt

# Never run as root inside the container.
RUN useradd --create-home --uid 10001 app \
 && mkdir -p /app/data \
 && chown -R app:app /app
USER app
WORKDIR /app

ENV VISION__MODEL_PATH=/app/models/yolov8n.pt \
    DATABASE__PATH=/app/data/fall_events.db \
    CAMERA__SHOW_WINDOW=false \
    HEALTH__HOST=0.0.0.0 \
    HEALTH__PORT=8080 \
    LOGGING__FORMAT=json

EXPOSE 8080
VOLUME ["/app/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/live', timeout=3)"

# SIGTERM from `docker stop` triggers the graceful shutdown (queued alerts are sent first).
STOPSIGNAL SIGTERM
ENTRYPOINT ["fall-detector"]
CMD ["run"]
