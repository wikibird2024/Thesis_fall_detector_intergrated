# 0003. Queue alerts; deliver and store in parallel

- Status: Accepted
- Date: 2026-09-28

## Context
Version 1 handled a fall inside the camera loop: insert into the DB (with
retries), then await Telegram and Asterisk (with retries and a 3 s pause). The
video froze meanwhile, and when the DB insert failed the function returned
before any alert was sent.

## Decision
`DetectionProcessor` only decides and calls `AlertDispatcher.submit()`, which
puts the alert on a bounded queue and returns. Worker tasks take alerts off
the queue and, in parallel: save the event, and send it on every channel with
a per-attempt timeout and retries. The event status becomes `alerted` if any
channel delivered, else `alert_failed`. Channels implement one small
`AlertChannel` protocol.

## Consequences
- Detection never waits on the network or disk.
- Storage problems can't suppress an alert.
- A new channel (SMS gateway, e-mail, webhook) is one class; retry and timeout
  come for free.
- Alerts in the queue are lost if the process is killed hard (SIGKILL, power
  loss). Graceful stop drains the queue. A persistent queue (e.g. write-ahead
  row in SQLite, or Redis) would be the next step if that risk matters.
