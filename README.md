
# Computer Vision-Based Fall Detection System 👁️

This project is a comprehensive fall detection system that uses deep learning models, specifically **YOLOv8**, to analyze video streams and detect fall events in real time. The system is designed with a modular and scalable architecture, allowing for easy integration with various devices and notification platforms.

-----

## 🚀 Key Features

  * **Object Detection and Tracking:** Employs a **YOLOv8** model (`yolov8n.pt`) to identify people (`human_detector.py`) and track their movements (`person_tracker.py`).
  * **Fall Posture Detection:** Analyzes skeletal keypoints (`skeleton_tracker.py`) to determine and classify fall events (`fall_detector.py`).
  * **Multi-channel Alerting:** Sends instant alerts through multiple channels, including **MQTT** (`mqtt_client.py`) and a **Telegram Bot** (`telegram_bot.py`), ensuring timely notifications to caregivers.
  * **Event Logging:** Records fall events into a **SQLite** database (`fall_events.db`) for later analysis and review (`database_manager.py`).
  * **Modular Architecture:** The codebase is organized into distinct components (`comm`, `detection`, `fall`, `processing`, `utils`) for easy maintenance and future development.
  * ** get_idf.py using for  get id telegram
-----

## 📁 Project Structure

The project is structured logically with a component-based architecture, where each directory is responsible for a specific function:

  * `comm/`: Contains communication components, including MQTT, Telegram Bot, and other notification services.
  * `config/`: Holds the system configuration files.
  * `database/`: Manages database connections and operations.
  * `detection/`: Houses the object detection modules, including human and skeleton tracking.
  * `fall/`: Contains the core logic for fall detection.
  * `processing/`: Handles the processing of video or camera input data.
  * `utils/`: Includes general utility functions, such as drawing bounding boxes and other helper functions.

-----

## 🛠️ Installation and Usage

### Environment Setup

Clone the repository to your local machine:

```bash
git clone <your_repository_URL>
cd intergrate_fall
```

Install the necessary libraries from `requirements.txt`:

```bash
pip install -r requirements.txt
```

### Running the System

To run the system, you must first configure the required parameters in the `config.py` file, and then execute `main.py`:

```bash
python main.py
```

-----

## 📝 Testing

The project includes unit tests (`test_fall.py`) to ensure core functionalities work as expected. You can run them using `pytest`:

```bash
pytest tests/
```

-----

## 🤝 Contributing

