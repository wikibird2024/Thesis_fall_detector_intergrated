# 0002. Supervise each background task on its own

- Status: Accepted
- Date: 2026-09-28

## Context
Version 1 ran all tasks in `asyncio.wait(..., FIRST_COMPLETED)`. When the MQTT
client stopped after 10 failed reconnects, its task finished, and the camera
task was cancelled with it. A 50-second broker outage turned fall detection off
until someone restarted the program.

## Decision
A `TaskSupervisor` runs each long-lived task independently. A crash is logged
and the task restarts with exponential backoff (1 s → 60 s; reset after 60 s of
stable running). Only the camera may end on purpose (`q` pressed), which asks
the application to stop. The MQTT client reconnects forever.

## Consequences
- One failing input can't stop the others.
- A task that crashes in a loop keeps restarting instead of stopping the
  program, so it has to be *visible*: logs, `task_restarts_total`,
  `/health/ready`. Monitoring is now required, not optional.
