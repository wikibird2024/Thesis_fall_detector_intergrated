# 0001. `src/` layout and `pyproject.toml`

- Status: Accepted
- Date: 2026-09-28

## Context
Modules lived at the repository root (`comm/`, `config/`, ...). Imports worked
only when Python was started from that folder, and tests could accidentally
import files that would not be installed. `requirements.txt` listed the wrong
MQTT library and missed pandas, so a fresh install failed.

## Decision
Put the code in one package, `src/fall_detector/`, installed with
`pip install -e .`. `pyproject.toml` holds dependencies (core, `[vision]`,
`[dev]`) and all tool settings. `requirements.lock.txt` pins exact versions
for Docker and production.

## Consequences
- Tests run against the installed package, the same way production runs.
- CI installs only core + dev (no torch), so it takes about a minute.
- One more step for newcomers (`pip install -e .`); `python main.py` still
  works through a small launcher.
