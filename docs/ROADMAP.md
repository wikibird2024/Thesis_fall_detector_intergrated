# Roadmap and learning guide

The project moved from a thesis script to a production-style service in six
steps. Each step is **one commit** on the branch, so you can study them one at
a time:

```bash
git log --oneline main..refactor/enterprise-upgrade
git show --stat <commit>     # what changed
git show <commit> -- <file>  # how it changed
```

```
Phase 0 Foundation ─> 1 Safety net ─> 2 Correctness ─> 3 Architecture ─> 4 Observability ─> 5 Delivery ─> 6 Scale (next)
```

## Done

| Phase | Commit | What changed | Enterprise skill to learn from it |
|---|---|---|---|
| 0 Foundation | `dc5c5d0` | `src/` package, `pyproject.toml`, ruff, mypy, pre-commit, Makefile | Reproducible installs; code-quality gates that run automatically |
| 1 Safety net | `fbe3b4e` | Characterization tests; known bugs recorded as strict `xfail` | Test *before* you change code; make bugs visible and measurable |
| 2 Correctness | `51e9d84` | Fall-angle and confidence bugs fixed; `xfail` flipped to pass | Debug by evidence: reproduce, prove, fix one cause, add a regression test |
| 3 Architecture | `54d5f57` | Layers, typed settings, DI, supervisor, alert queue, repository, migrations | SOLID, ports & adapters, fault isolation, retries with backoff |
| 4 Observability | `a9bc47a` | `/health/*`, Prometheus metrics, JSON logs | Liveness vs readiness; the metrics that matter; correlation ids |
| 5 Delivery | (phase-5 commit) | Docker, compose, CI, lock file, generated config docs, ADRs, runbook | CI/CD, containers, docs as a product, decision records |

### Bugs found and fixed on the way

| Bug | Effect | Fixed in |
|---|---|---|
| Confidence check read z (depth) instead of visibility | Camera falls were rarely reported | Phase 2 |
| Upright torso measured as 180° | Would alarm on every standing person once the first bug was fixed | Phase 2 |
| `value or default` in thresholds | An explicit 0 was ignored | Phase 2 |
| MQTT gave up after 10 tries and `FIRST_COMPLETED` cancelled the camera | ~50 s broker outage turned detection off | Phase 3 |
| DB insert failure returned before alerting | Disk problem = silent fall | Phase 3 |
| Alerts awaited inside the camera loop | Video froze for seconds on every alert | Phase 3 |
| Telegram retried in two layers, inner one swallowed errors | False "sent successfully" logs | Phase 3 |
| ESP32 read returned one 8 KB chunk per call | About 1 frame per second from the stream | Phase 3 |
| MQTT processor never started if broker was slow at startup | Wearable alerts ignored until restart | Phase 3 |
| Stale-entity eviction (30 s) shorter than cooldown (60 s) | Repeat alerts from the same device | Phase 3 |
| Multi-line alert text in AMI headers | Would corrupt the AMI action | Phase 3 |
| Config errors echoed input values | Could print passwords into logs | Phase 3 |
| AMI `connect()` called again after an error while panoramisk also reconnected | Connections replaced each other every 2 s | Phase 5 review |
| `requirements.txt` listed the wrong MQTT library, missed pandas | Fresh install failed | Phase 0 |

## Next: Phase 6, scale and accuracy

Ordered by value for effort. Each is a good self-contained learning project.

| # | Item | Why | Skill |
|---|---|---|---|
| 1 | Record 20–50 labeled clips (falls, sitting, lying on sofa) and a replay test | Tune thresholds with numbers, not guesses | Evaluation: precision/recall, confusion matrix |
| 2 | Scale-free speed (divide by torso length) and one "down" counter | Fewer misses and false alarms (see ARCHITECTURE §6) | Feature engineering |
| 3 | ByteTrack instead of IoU tracker | Keeps ids through short occlusions | Multi-object tracking |
| 4 | YOLOv8-Pose instead of YOLO + MediaPipe | One model, multi-person, faster | Model selection |
| 5 | ONNX / TensorRT / OpenVINO export | 2–5× faster on edge hardware (Jetson, NUC) | Model optimization |
| 6 | RTSP IP cameras, several at once | Real installations use IP cameras | Video pipelines (GStreamer) |
| 7 | PostgreSQL + Alembic | Several detectors writing to one place | Database operations |
| 8 | Acknowledge button in Telegram → status `acknowledged` | Know that a human reacted | Closed-loop alerting |
| 9 | Grafana dashboard + Alertmanager rules from RUNBOOK | See trends, get paged | Monitoring |
| 10 | Release pipeline: version tag → image pushed to a registry | Repeatable deploys | Continuous delivery |

## Definition of done (for any change)

- [ ] `make check` passes (ruff, mypy, tests)
- [ ] New behavior has a test; a bug fix has a regression test that failed before
- [ ] Settings changed → `fall-detector config-docs > docs/CONFIGURATION.md`
- [ ] User-visible change → `CHANGELOG.md`
- [ ] Hardware-dependent parts (camera, phones) checked on the bench, or stated as not checked
