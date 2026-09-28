"""Builds docs/CONFIGURATION.md from the Settings model.

The settings code is the single source of truth; the document is generated,
and a test fails when someone changes a setting without regenerating it:

    fall-detector config-docs > docs/CONFIGURATION.md
"""

from __future__ import annotations

import json
from typing import Any, Literal, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from fall_detector.settings import Settings

HEADER = """# Configuration

> Generated from `src/fall_detector/settings.py`. Do not edit by hand:
> run `fall-detector config-docs > docs/CONFIGURATION.md`.

Settings are read from environment variables and from `.env` (see `.env.example`).
Groups use a double underscore: `GROUP__SETTING=value`. Lists are JSON, e.g.
`AMI__EXTENSIONS=["6001","6002"]`. Every value is checked at startup; run
`fall-detector check-config` to see the values in effect (secrets hidden).

Version 1 names (`MQTT_USERNAME`, `TELEGRAM_BOT_TOKEN`, ...) still work and log
a warning asking you to rename them.
"""


def _default(field: FieldInfo) -> str:
    if field.default_factory is not None:
        value: Any = field.default_factory()  # type: ignore[call-arg]
    elif field.default is PydanticUndefined:
        return "required"
    else:
        value = field.default
    if value is None:
        return "-"
    if isinstance(value, (list, dict)):
        return f"`{json.dumps(value)}`"
    return f"`{value}`"


def _type_name(field: FieldInfo) -> str:
    if get_origin(field.annotation) is Literal:
        return "one of: " + ", ".join(str(choice) for choice in get_args(field.annotation))
    text = str(field.annotation).replace("typing.", "").replace("pydantic.types.", "")
    for noise in ("<class '", "'>", "pathlib."):
        text = text.replace(noise, "")
    return text.replace("SecretStr", "secret").replace(" | None", " (optional)")


def _limits(field: FieldInfo) -> str:
    parts = []
    for item in field.metadata:
        for attr, symbol in (("ge", ">="), ("gt", ">"), ("le", "<="), ("lt", "<")):
            value = getattr(item, attr, None)
            if value is not None:
                parts.append(f"{symbol} {value}")
    return ", ".join(parts)


def render_configuration_markdown() -> str:
    lines = [HEADER]
    for group_name, group_field in Settings.model_fields.items():
        model = group_field.annotation
        assert isinstance(model, type) and issubclass(model, BaseModel)
        lines.append(f"## {group_name}\n")
        if model.__doc__ and model.__doc__ != BaseModel.__doc__:
            lines.append(f"{model.__doc__.strip()}\n")
        lines.append("| Variable | Type | Default | Allowed | Meaning |")
        lines.append("|---|---|---|---|---|")
        for name, field in model.model_fields.items():
            variable = f"`{group_name.upper()}__{name.upper()}`"
            lines.append(
                f"| {variable} | {_type_name(field)} | {_default(field)} | {_limits(field)} "
                f"| {field.description or ''} |"
            )
        lines.append("")
    return "\n".join(lines)
