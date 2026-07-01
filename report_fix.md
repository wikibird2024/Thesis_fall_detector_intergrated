# Fix Report

Summary of all bugs identified in the code review and the changes applied to resolve them.

---

## Fix 1 — `.gitignore` merge conflict

**File:** `.gitignore`

**Problem:** The file contained unresolved `<<<<<<< HEAD` / `=======` / `>>>>>>> origin/master` conflict markers from a previous merge. Git was not ignoring anything listed in the conflicting section, meaning files like `.env` (containing secrets) and `fall_events.db` could accidentally be committed.

**Fix:** Rewrote `.gitignore` as a clean, merged file keeping the union of rules from both conflict sides, plus removed duplicate entries.

---

## Fix 2 — `FallDetector` instances leaked for lost camera tracks

**Files:** `processing/detection_processor.py`

**Problem:** `DetectionProcessor` maintained a `fall_detectors` dict keyed by `entity_id`. When a person left the camera frame, `PersonTracker` discarded their ID, but the corresponding `FallDetector` (and its associated `last_alert_timestamps` / `last_fall_timestamps` entries) remained in memory forever. Over a long session, the dict would grow without bound.

**Fix:**
- Added `entity_last_seen: Dict[str, datetime]` to `DetectionProcessor.__init__`.
- `handle_camera_data` and `handle_mqtt_data` both update `entity_last_seen[entity_id]` on every call.
- Added `evict_stale_detectors(max_age_seconds=30.0)` which deletes all four dict entries for any entity not seen within the window.
- `camera_processing_loop` in `main.py` calls `detection_processor.evict_stale_detectors()` once per frame, after processing all tracked persons.

---

## Fix 3 — `PersonTracker.update()` used list mutation and first-match instead of best-match

**File:** `detection/person_tracker.py`

**Problem:** The original matching loop called `detected_boxes.pop(i)` to mark a detection as consumed. While the `break` prevented an out-of-bounds access within a single outer iteration, the approach also matched each existing track to the *first* detection above the IoU threshold rather than the *best* (highest IoU) one. This caused incorrect ID re-assignments when multiple detections were nearby.

**Fix:** Replaced the mutable-list approach with a `matched_indices: set` that is checked before computing IoU. Each tracked person now greedily picks the highest-IoU unmatched detection. Unmatched detections become new persons at the end, with no list modification mid-loop.

---

## Fix 4 — `test_fall.py` called a non-existent method

**File:** `tests/test_fall.py`

**Problem:** The test called `detector.is_fall([])`, but the actual method on `FallDetector` is `detect_fall()`. The test raised `AttributeError` on every run and had never passed.

**Fix:** Changed `detector.is_fall([])` → `detector.detect_fall([])`.

---

## Fix 5 — No startup validation for required environment variables

**File:** `config/config.py`, `main.py`

**Problem:** When `ENABLE_MQTT`, `ENABLE_TELEGRAM`, or `ENABLE_AMI` were `True` but the corresponding `.env` secrets were absent, the system would start, then crash or silently fail deep inside a connection attempt with a confusing `None`-related error (e.g., `TypeError: expected str, got NoneType`).

**Fix:**
- Added `validate_config()` to `config/config.py`. It checks that each enabled feature has its required env vars set and raises `EnvironmentError` with a clear list of what is missing.
- Called `validate_config()` at the top of `main()` in `main.py`, before any module is initialized.

---

## Fix 6 — `cooldown_minutes` hardcoded in `DetectionProcessor.__init__`

**Files:** `config/config.py`, `processing/detection_processor.py`

**Problem:** The 1-minute alert cooldown was written as `self.cooldown_minutes = 1` directly in `DetectionProcessor.__init__`, while all other tunables live in `config/config.py`. Changing it required editing application logic code.

**Fix:**
- Added `ALERT_COOLDOWN_MINUTES: int = 1` to `config/config.py`.
- `DetectionProcessor.__init__` now imports and uses `ALERT_COOLDOWN_MINUTES`.

---

## Fix 7 — YOLOv8 and MediaPipe inference blocked the `asyncio` event loop

**File:** `main.py`

**Problem:** `human_detector.detect_humans(frame)` (YOLOv8) and `skeleton_tracker.track_from_box(frame, box)` (MediaPipe) are CPU/GPU-bound blocking calls. Running them directly on the event loop stalled all other async tasks (MQTT processing, Telegram retries, heartbeat) for the duration of each inference call — typically tens of milliseconds per frame.

**Fix:** Both calls are now wrapped with `asyncio.to_thread(...)`, moving them to the default thread pool executor. The event loop remains responsive during inference.

---

## Fix 8 — `get_telegram_id_bot.py` undocumented

**Files:** `CLAUDE.md`

**Problem:** The utility script `get_telegram_id_bot.py` exists specifically to retrieve a user's Telegram `CHAT_ID` (a required secret), but it was not mentioned in any setup documentation. New developers had no way to discover it.

**Fix:** Added a one-line note to `CLAUDE.md` under the Environment Setup section: `python get_telegram_id_bot.py` prints the chat ID after you message the bot.

---

## Summary table

| # | Severity | File(s) changed | Category |
|---|---|---|---|
| 1 | High | `.gitignore` | Security / correctness |
| 2 | Medium | `processing/detection_processor.py`, `main.py` | Memory leak |
| 3 | Medium | `detection/person_tracker.py` | Logic bug |
| 4 | High | `tests/test_fall.py` | Broken test |
| 5 | Medium | `config/config.py`, `main.py` | Reliability |
| 6 | Low | `config/config.py`, `processing/detection_processor.py` | Maintainability |
| 7 | Medium | `main.py` | Performance / correctness |
| 8 | Low | `CLAUDE.md` | Documentation |
