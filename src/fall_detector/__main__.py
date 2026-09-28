"""Command line.

    fall-detector                 run the system (same as `fall-detector run`)
    fall-detector check-config    validate settings and print them (secrets hidden)
    fall-detector events -n 20    show the latest fall events from the database

Also: `python -m fall_detector ...` or `python main.py ...`.
Exit codes: 0 ok, 2 invalid configuration.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Sequence

from pydantic import ValidationError

from fall_detector import __version__
from fall_detector.observability.logging_setup import configure_logging
from fall_detector.settings import Settings, load_settings

logger = logging.getLogger("fall_detector")

EXIT_OK = 0
EXIT_BAD_CONFIG = 2


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="fall-detector", description="Real-time fall detection and alerting."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--env-file", default=".env", help="settings file (default: .env)")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("run", help="run the system (default)")
    commands.add_parser("check-config", help="validate settings and print them")
    events = commands.add_parser("events", help="show recent fall events")
    events.add_argument("-n", "--limit", type=int, default=20)
    return parser.parse_args(argv)


def describe_config_error(error: ValidationError) -> str:
    """List the problems without echoing input values: they may contain passwords or tokens."""
    lines = []
    for problem in error.errors():
        where = "__".join(str(part) for part in problem["loc"]).upper() or "settings"
        lines.append(f"  - {where}: {problem['msg']}")
    return "\n".join(lines)


def cmd_run(settings: Settings) -> int:
    from fall_detector.app import run

    logger.info("Fall detector %s starting", __version__)
    try:
        asyncio.run(run(settings))
    except KeyboardInterrupt:  # only reached where signal handlers are unavailable (Windows)
        logger.info("Interrupted")
    return EXIT_OK


def cmd_check_config(settings: Settings) -> int:
    print(json.dumps(settings.model_dump(mode="json"), indent=2))
    print("\nConfiguration OK", file=sys.stderr)
    return EXIT_OK


def cmd_events(settings: Settings, limit: int) -> int:
    from fall_detector.storage.repository import FallEventRepository

    repository = FallEventRepository(settings.database.path)
    repository.migrate()
    rows = repository.recent(limit)
    if not rows:
        print("No fall events recorded.")
    for e in rows:
        where = f"{e.latitude},{e.longitude}" if e.has_gps_fix else "-"
        print(f"{e.id:>5}  {e.timestamp:<32}  {e.source or '?':<7} {e.entity_id or '?':<20} "
              f"{e.status:<13} {where:<22} {e.event_id or ''}")  # fmt: skip
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging()  # defaults until settings are known
    try:
        settings = load_settings(args.env_file)
    except ValidationError as error:
        logger.error("Invalid configuration:\n%s", describe_config_error(error))
        return EXIT_BAD_CONFIG
    configure_logging(settings.logging.level, settings.logging.format)

    if args.command == "check-config":
        return cmd_check_config(settings)
    if args.command == "events":
        return cmd_events(settings, args.limit)
    return cmd_run(settings)


if __name__ == "__main__":
    sys.exit(main())
