"""Command-line entry point: `python -m fall_detector` or `fall-detector`."""

import asyncio

from fall_detector.app import logger
from fall_detector.app import main as run_app


def main() -> None:
    logger.info("[SYSTEM] Starting Fall Detection System...")
    try:
        asyncio.run(run_app())
    except KeyboardInterrupt:
        logger.info("[SYSTEM] Program interrupted by user")
    finally:
        logger.info("[SYSTEM] Goodbye!")


if __name__ == "__main__":
    main()
