# System Flow Documentation
## ESP SmartHome — Camera Node to Mesh Network

---

## System Overview

```
┌─────────────────┐        UDP/WiFi        ┌──────────────────────┐      ESP-NOW      ┌─────────┐
│  Raspberry Pi   │ ─────────────────────► │  ESP32 Feather V2    │ ────────────────► │ Gateway │
│  (Camera Node)  │    person detections   │  (Bridge Node)       │   mesh alerts     │  Node   │
└─────────────────┘                        └──────────────────────┘                   └─────────┘
```

The Raspberry Pi runs AI-based person detection on a live camera feed.
Detections are sent over UDP to the ESP32 Feather V2, which acts as a bridge
between the WiFi network and the ESP-NOW mesh. The ESP32 forwards person
detection events onto the mesh as standard alert frames understood by all nodes.

---

## Components

| Component | Hardware | Key Files |
|---|---|---|
| Camera Node | Raspberry Pi (any model with CSI camera) | `rpi/detection_v2.py`, `rpi/udp_comm.py` |
| Bridge Node | ESP32 Feather V2 | `esp32_rpi_bridge/main.py`, `esp32_rpi_bridge/camera_mesh.py` |
| Mesh Protocol | shared | `node_a_micropython/message.py`, `node_a_micropython/mesh_comm.py` |

---

## Detailed Flow

### Stage 1 — Camera Pipeline (Raspberry Pi)

```
rpicam-vid (YUV420 stream)
        │
        ▼
  Read Y-plane (grayscale frame)
        │
        ▼
  Gaussian blur + background subtraction
        │
        ├── No motion detected ──► sleep, loop
        │
        └── Motion detected
                │
                ▼
        Convert frame to RGB
                │
                ▼
        MobileNet SSD inference (OpenCV DNN)
                │
                ├── No person (confidence < 0.5) ──► loop
                │
                └── Person detected
                        │
                        ▼
                udp_comm.send_person(confidence)
```

**Why two-stage?** Motion detection is cheap (pixel math). AI inference is expensive (tens of ms on Pi 3). Motion acts as a gate so the model only runs when something is actually moving.

**What is NOT forwarded:** Motion events are suppressed — only confirmed AI person classifications are sent. This reduces false positives from pets, shadows, etc.

---

### Stage 2 — UDP Transport (RPi → ESP32)

```
RPi (udp_comm.py)                        ESP32 (main.py)
        │                                       │
        │   JSON over UDP, port 5005            │
        │ ────────────────────────────────────► │
        │                                       │
        │  {"event": "person",                  │
        │   "confidence": 0.87,                 │
        │   "ts": 1744567890}                   │
        │                                       │
        │   ACK, port 5006                      │
        │ ◄──────────────────────────────────── │
        │  {"ack": "ok", "event": "person"}     │
```

**Port map:**

| Direction | Port | Purpose |
|---|---|---|
| RPi → ESP32 | 5005 | detection events |
| ESP32 → RPi | 5006 | acknowledgments |

**Event types sent by RPi:**

| Event | Forwarded to mesh? | Reason |
|---|---|---|
| `motion` | No | Not accurate enough on its own |
| `person` | Yes | AI-confirmed classification |
| `clear` | No | ESP32 manages its own clear logic |

---

### Stage 3 — Bridge State Machine (ESP32 `camera_mesh.py`)

The ESP32 does not blindly forward every UDP packet to the mesh. Instead it
runs a state machine to produce clean transition-based events.

```
         ┌─────────────────────────────────┐
         │                                 │
         ▼                                 │  person packet received
      [ CLEAR ] ──(person detected)──► [ PERSON ] ──(refresh timer)──┐
         ▲                                 │                          │
         │                                 │                          ▼
         └────(8s with no detections)──────┘                   (no mesh TX)
```

**Transitions that generate mesh traffic:**

| Transition | Mesh message sent |
|---|---|
| CLEAR → PERSON | `MSG_TYPE_ALERT`, code `0x20` (PERSON_DETECTED) |
| PERSON → CLEAR | `MSG_TYPE_ALERT`, code `0x21` (PERSON_CLEARED) |

**Why timeout-based clearing?**
The RPi sends a `clear` event when no motion is detected, but motion detection
has false negatives (a still person won't trigger it). The ESP32 independently
times out after 8 seconds of no *person* packets — a much more reliable signal.

---

### Stage 4 — Mesh Transmission (ESP32 → Gateway)

The bridge node uses the same wire format as all other mesh nodes (defined in
`message.py`, wire-compatible with the C firmware).

```
Frame layout (up to 250 bytes):

  ┌──────────┬──────────┬──────┬─────┬─────┬───────────┬─────────────┬──────┐
  │ src_mac  │ dst_mac  │ type │ seq │ ttl │ timestamp │   payload   │ crc8 │
  │  6 bytes │  6 bytes │  1B  │ 2B  │  1B │   4 bytes │   3 bytes   │  1B  │
  └──────────┴──────────┴──────┴─────┴─────┴───────────┴─────────────┴──────┘

  msg_type = 0x02 (MSG_TYPE_ALERT)

  Payload (3 bytes):
  ┌────────────┬────────────────────┐
  │ alert_code │   sensor_reading   │
  │   1 byte   │   2 bytes (uint16) │
  └────────────┴────────────────────┘

  PERSON_DETECTED  alert_code=0x20  sensor_reading = confidence × 100
  PERSON_CLEARED   alert_code=0x21  sensor_reading = 0
```

Transmitted via ESP-NOW directly to `GATEWAY_MAC` with up to 3 retries.

---

## Timing Summary

```
Camera frame rate:        5 FPS  (limited for Pi 3 stability)
Motion gate latency:     ~20 ms  (Gaussian blur + contour check)
AI inference latency:   ~300 ms  (MobileNet SSD on Pi 3 CPU)
UDP transit:             <10 ms  (LAN)
Person clear timeout:      8 s   (configurable in camera_mesh.py)
Mesh retry delay:        100 ms  (up to 3 attempts)
```

---

## File Map

```
ESP_SmartHome/
│
├── rpi/                          # Raspberry Pi camera node
│   ├── detection_v2.py           # camera pipeline + AI inference
│   ├── udp_comm.py               # UDP send/receive layer
│   └── model/
│       ├── deploy.prototxt       # MobileNet SSD network definition
│       └── mobilenet_iter_73000.caffemodel   # pretrained weights
│
├── esp32_rpi_bridge/             # ESP32 Feather V2 bridge node
│   ├── main.py                   # boot, WiFi, async UDP loop
│   ├── camera_mesh.py            # state machine + ESP-NOW forwarding
│   └── leak_ulp.py               # separate leak sensor (deep sleep)
│
└── node_a_micropython/           # existing mesh sensor node (reference)
    ├── message.py                # mesh frame protocol (copy to bridge board)
    ├── mesh_comm.py              # ESP-NOW wrapper
    ├── config.py                 # MAC addresses, pins, thresholds
    └── ...
```

---

## Alert Codes Reference

| Code | Name | Defined in | Meaning |
|---|---|---|---|
| `0x01` | Temp alert | `sensor_task.py` | Temperature out of range |
| `0x10` | Occupancy | `sensor_task.py` | PIR state transition |
| `0x20` | Person detected | `camera_mesh.py` | AI camera: person appeared |
| `0x21` | Person cleared | `camera_mesh.py` | AI camera: person gone (timeout) |
