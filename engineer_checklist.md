# Engineer Checklist — Computer Vision / AI Systems

> Legend: **[MUST]** = non-negotiable for most roles · **[SHOULD]** = expected at mid-level · **[NICE]** = differentiator

---

## 1. Core ML / Deep Learning

These are assumed known. If any box is shaky, fix it first — everything else builds on this.

- [ ] **[MUST]** PyTorch — training loop, loss, optimizer, scheduler, DataLoader
- [ ] **[MUST]** Transfer learning and fine-tuning a pretrained model on your own data
- [ ] **[MUST]** Evaluation metrics — mAP, F1, AUC, confusion matrix. Know when each is appropriate
- [ ] **[MUST]** Overfitting diagnosis — train/val curves, regularization, dropout, early stopping
- [ ] **[MUST]** Data augmentation — `Albumentations` is the standard library for CV
- [ ] **[SHOULD]** Hyperparameter tuning — Optuna or W&B sweeps
- [ ] **[SHOULD]** Knowledge distillation — train a small model to mimic a large one
- [ ] **[SHOULD]** Class imbalance handling — weighted loss, focal loss, oversampling
- [ ] **[NICE]** Mixed precision training (FP16) with `torch.cuda.amp`

---

## 2. Computer Vision — Models and Techniques

### Object Detection
- [ ] **[MUST]** YOLOv8 / YOLO11 — know how to train, export, and evaluate
- [ ] **[SHOULD]** Understand anchor-based vs anchor-free detection (conceptually)
- [ ] **[SHOULD]** DETR / RT-DETR — transformer-based detection, growing adoption
- [ ] **[NICE]** Faster R-CNN — still used in high-accuracy offline pipelines

### Pose Estimation
- [ ] **[MUST]** YOLOv8-Pose — single-pass detection + 17 keypoints, replaces YOLO + MediaPipe
- [ ] **[SHOULD]** MediaPipe Pose — know it, but know its limits (single person, slower)
- [ ] **[SHOULD]** ViTPose — transformer-based, best accuracy, used in research pipelines
- [ ] **[NICE]** 3D pose estimation (lifting 2D to 3D) — useful for fall biomechanics

### Action Recognition / Video Understanding
- [ ] **[MUST]** Understand the difference: frame-level vs clip-level vs sequence models
- [ ] **[MUST]** LSTM / GRU on keypoint sequences — the practical approach for skeleton-based action
- [ ] **[SHOULD]** ST-GCN — skeleton as a graph, current standard for skeleton-based recognition
- [ ] **[SHOULD]** SlowFast / VideoSwin — when you need raw video understanding
- [ ] **[NICE]** TimeSformer / VideoMAE — transformer-based video models

### Multi-Object Tracking
- [ ] **[MUST]** ByteTrack — know how it works, how to use it via `ultralytics`
- [ ] **[SHOULD]** StrongSORT / BoT-SORT — tracking with appearance features (Re-ID)
- [ ] **[SHOULD]** DeepSORT — older but still referenced, understand its limitations
- [ ] **[NICE]** OC-SORT — handles occlusions better, growing adoption

### Re-Identification (Re-ID)
- [ ] **[SHOULD]** Concept: matching a person across cameras or time gaps using appearance embeddings
- [ ] **[SHOULD]** OSNet — lightweight Re-ID model, runs on edge
- [ ] **[NICE]** CLIP-ReID — using CLIP embeddings for zero-shot Re-ID

### Classical CV (still used constantly)
- [ ] **[MUST]** OpenCV — camera calibration, homography, morphological ops, contours
- [ ] **[MUST]** Optical flow — Farneback (fast, OpenCV) and RAFT (deep, accurate)
- [ ] **[SHOULD]** Background subtraction — MOG2, KNN for static camera scenes
- [ ] **[SHOULD]** Image geometry — perspective transform, bird's eye view projection

---

## 3. Model Optimization and Deployment

This is where thesis projects end and engineering begins.

- [ ] **[MUST]** ONNX — export any PyTorch model. Every production pipeline uses this
- [ ] **[MUST]** TensorRT (NVIDIA) — compile ONNX to GPU-optimized engine, FP16/INT8
- [ ] **[MUST]** INT8 quantization — calibration dataset, accuracy vs speed tradeoff
- [ ] **[SHOULD]** OpenVINO (Intel) — same idea as TensorRT but for Intel CPUs/VPUs
- [ ] **[SHOULD]** TFLite — for mobile/embedded, still common in IoT edge nodes
- [ ] **[SHOULD]** Model pruning — structured pruning with `torch.nn.utils.prune`
- [ ] **[NICE]** CoreML — if you ever touch Apple hardware (iPhone, Vision Pro)
- [ ] **[NICE]** Hailo-8 — dedicated AI accelerator chip, growing in embedded safety systems

**Practical benchmark to aim for:** take your YOLOv8n, export to TensorRT FP16, measure the latency difference. That exercise alone teaches you the full workflow.

---

## 4. Edge AI Hardware

Know the hardware your code will run on — it shapes every architectural decision.

- [ ] **[MUST]** NVIDIA Jetson Orin / Nano — the standard for vision at the edge. Know `jetson-stats`, power modes, thermal limits
- [ ] **[SHOULD]** Raspberry Pi 5 + Google Coral TPU — budget edge node for low-throughput cameras
- [ ] **[SHOULD]** Intel NUC / NCS2 — common in European industrial deployments with OpenVINO
- [ ] **[NICE]** NVIDIA Jetson AGX Orin — high-end, runs 6–8 camera streams with DeepStream
- [ ] **[NICE]** Power budgeting — understand TDP, thermal design, why INT8 matters on battery

---

## 5. Production Video Pipelines

Your `cv2.VideoCapture` works on a webcam. Real cameras speak different protocols.

- [ ] **[MUST]** RTSP — how to connect, authenticate, decode. `ffmpeg -i rtsp://...` is your first test
- [ ] **[MUST]** FFmpeg — the universal video tool. Transcoding, frame extraction, stream probing
- [ ] **[SHOULD]** ONVIF — the protocol for discovering and configuring IP cameras programmatically
- [ ] **[SHOULD]** GStreamer — pipeline-based video processing. Used under DeepStream and many industrial SDKs
- [ ] **[SHOULD]** NVIDIA DeepStream — multi-camera batched inference on Jetson or GPU server. The industry standard for video analytics at scale
- [ ] **[SHOULD]** H.264 / H.265 codec knowledge — why it matters for latency, bandwidth, and keyframe handling
- [ ] **[NICE]** WebRTC — for low-latency browser-based video streaming of processed output
- [ ] **[NICE]** Apache Kafka — for streaming analytics when you have 50+ cameras feeding a central system

---

## 6. MLOps — Keeping Models Alive in Production

A model that isn't monitored is a liability.

- [ ] **[MUST]** Docker — containerize everything. If it only runs on your machine, it doesn't count
- [ ] **[MUST]** MLflow — experiment tracking, model versioning, artifact storage
- [ ] **[MUST]** DVC (Data Version Control) — version your datasets alongside your code
- [ ] **[SHOULD]** Weights & Biases — richer dashboards than MLflow, widely used in CV teams
- [ ] **[SHOULD]** CI/CD for ML — GitHub Actions that run evaluation on every model change
- [ ] **[SHOULD]** Model monitoring — detect when accuracy drops in production (data drift)
- [ ] **[SHOULD]** Data annotation tools — CVAT (open source), Roboflow, Label Studio. You will label data
- [ ] **[NICE]** Kubeflow — ML pipelines on Kubernetes, used in large cloud-deployed ML systems
- [ ] **[NICE]** Triton Inference Server (NVIDIA) — serve multiple models on one GPU, batching, dynamic shapes

---

## 7. Software Engineering

The code quality gap between a thesis and a production system.

### APIs and Services
- [ ] **[MUST]** FastAPI — build REST APIs for your models. Async, typed, auto-documented
- [ ] **[MUST]** REST API design — status codes, versioning (`/api/v1/`), pagination, error schemas
- [ ] **[MUST]** WebSockets — for real-time push of detection events to dashboards
- [ ] **[SHOULD]** Redis — pub/sub for real-time alerts across services, caching inference results
- [ ] **[SHOULD]** PostgreSQL + TimescaleDB — time-series event storage (better than SQLite for production)
- [ ] **[NICE]** gRPC — high-performance service-to-service communication, used in microservice architectures

### Infrastructure
- [ ] **[MUST]** Docker Compose — run multi-service systems (camera processor + API + database) locally
- [ ] **[SHOULD]** Kubernetes basics — deploying containers at scale, health checks, rolling updates
- [ ] **[SHOULD]** Cloud basics — AWS or GCP. S3 for model storage, EC2/Compute Engine for GPU inference
- [ ] **[NICE]** Terraform — infrastructure as code, provision GPU servers programmatically

### Code quality
- [ ] **[MUST]** Git branching strategy — feature branches, PRs, code review workflow
- [ ] **[MUST]** Type hints + `mypy` — Python without types does not survive a team environment
- [ ] **[SHOULD]** `pytest` — proper unit and integration tests, not just `if __name__ == "__main__"`
- [ ] **[SHOULD]** Pre-commit hooks — `ruff`, `black`, `isort` run automatically before commit
- [ ] **[NICE]** Async profiling — `py-spy`, `asyncio` task introspection to find bottlenecks

---

## 8. Networking and Protocols

Engineers who understand the network layer are much more effective with camera systems.

- [ ] **[MUST]** TCP/IP basics — why UDP matters for real-time video, why TCP matters for control
- [ ] **[MUST]** MQTT — you already know this. Understand QoS levels (0/1/2) and broker clustering
- [ ] **[SHOULD]** Network troubleshooting — Wireshark, `tcpdump`, `ping`, `traceroute`
- [ ] **[SHOULD]** VPN / tunneling — accessing remote cameras behind NAT (Tailscale, WireGuard)
- [ ] **[NICE]** 5G / LTE camera connectivity — for mobile safety cameras on construction sites

---

## 9. Data Engineering for Vision

Models are only as good as the data pipeline that feeds them.

- [ ] **[MUST]** Dataset formats — COCO JSON, YOLO txt, Pascal VOC XML. Convert between them
- [ ] **[MUST]** Train/val/test split strategy — why random split is wrong for video (temporal leakage)
- [ ] **[SHOULD]** Synthetic data — generating training data with Blender, Unity, or NVIDIA Omniverse when real data is scarce
- [ ] **[SHOULD]** Hard negative mining — collecting the cases your model gets wrong and retraining on them
- [ ] **[SHOULD]** Active learning — labeling only the samples the model is most uncertain about
- [ ] **[NICE]** Video anonymization — blurring faces/replacing skeletons for GDPR-compliant dataset sharing

---

## 10. Domain Knowledge — Safety and Healthcare AI

If you work in fall detection, workplace safety, or healthcare AI, these matter.

- [ ] **[SHOULD]** GDPR / data privacy basics — especially for video in care settings
- [ ] **[SHOULD]** ISO 45001 — occupational health and safety management standard
- [ ] **[SHOULD]** SIL (Safety Integrity Level) — concept of safety-critical system certification. You won't implement it but must know it exists
- [ ] **[NICE]** FDA SaMD (Software as a Medical Device) — if product is used in clinical settings, FDA clearance is required in the US
- [ ] **[NICE]** CE marking — European equivalent for medical/safety devices

---

## 11. Research Awareness — Know What Is Happening

You don't need to implement these but must know they exist and what they are for.

- [ ] **[MUST]** Follow CVPR, ICCV, ECCV — the top three CV conferences. Read abstracts, not full papers
- [ ] **[MUST]** Foundation models — CLIP (image + text), SAM (segment anything), DINO (self-supervised features)
- [ ] **[SHOULD]** Video foundation models — VideoMAE, InternVideo. Pretrained on massive video datasets
- [ ] **[SHOULD]** Multimodal LLMs — GPT-4V, Gemini, LLaVA. Can describe video scenes; useful for alert generation
- [ ] **[SHOULD]** mmWave radar for fall detection — Google, Samsung, Apple all shipping this in consumer devices
- [ ] **[NICE]** Diffusion models for data augmentation — generate synthetic training images of falls
- [ ] **[NICE]** Neuromorphic cameras (event cameras) — ultra-low latency, growing in robotics and safety

---

## 12. Tools Reference Card

Quick reference for which tool does what.

| Category | Tool | What for |
|---|---|---|
| Training | PyTorch + Albumentations | Model training and augmentation |
| Experiment tracking | MLflow or W&B | Track runs, compare models |
| Data versioning | DVC | Version datasets with Git |
| Export | ONNX | Hardware-agnostic model format |
| GPU inference | TensorRT | Fast inference on NVIDIA hardware |
| CPU inference | OpenVINO | Fast inference on Intel hardware |
| Video pipeline | GStreamer / DeepStream | Multi-camera production pipelines |
| Camera protocol | RTSP / ONVIF | Connect to real IP cameras |
| Video tool | FFmpeg | Transcode, probe, extract frames |
| Tracking | ByteTrack (ultralytics) | Multi-object tracking |
| Annotation | CVAT / Roboflow | Label your training data |
| API | FastAPI | Expose model as HTTP service |
| Container | Docker + Compose | Package and run anywhere |
| Orchestration | Kubernetes | Scale across servers |
| Realtime alerts | MQTT / Redis pub-sub | Push events to other systems |
| Database | PostgreSQL + TimescaleDB | Production event storage |
| Edge board | NVIDIA Jetson Orin | Run everything on-device |

---

## Priority order if you have 6 months

| Month | Focus | Output |
|---|---|---|
| 1 | Docker + FastAPI + PostgreSQL | Containerized API for your fall detector |
| 2 | ONNX + TensorRT export + benchmark | Know your model's latency on real hardware |
| 3 | MLflow + DVC + retrain pipeline | Full experiment tracking for one model iteration |
| 4 | ByteTrack + YOLOv8-Pose swap | Better tracker, single-pass pose |
| 5 | RTSP + DeepStream basic pipeline | Connect to a real IP camera, multi-stream |
| 6 | LSTM fall detector trained on URFD | Replace rule-based detector with trained model |

After those 6 months you can honestly claim senior-student-to-junior-engineer level across the full stack of a CV system. Each month produces something demonstrable — that matters more than courses.

---

## Honest reality check

Most engineers in this field are strong in 3–4 of the above categories and aware of the rest. You do not need to master all of this before applying for jobs. What you need is:

1. One production-quality project (containerized, API-exposed, monitored) — not ten thesis projects.
2. The ability to talk about tradeoffs, not just "I used YOLO."
3. Awareness of the full stack even if you haven't implemented every piece.

Your thesis is already the foundation of that first project. The gap is packaging, not knowledge.
