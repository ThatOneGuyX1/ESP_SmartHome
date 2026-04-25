# ESP32 Feather V2 — Camera Bridge Node

Bridges the Raspberry Pi camera node (UDP/WiFi) to the ESP-NOW mesh network.
Receives confirmed person detections from the RPi over UDP and forwards them
toward the host node using hop-based mesh routing.

```
Raspberry Pi  ──UDP/WiFi──►  ESP32 Feather V2  ──ESP-NOW──►  Mesh / Host
(camera node)                (this device)
```

> The ESP32 is a required middleman. The RPi cannot speak ESP-NOW directly —
> it uses standard WiFi, and ESP-NOW is an ESP32-only protocol.

See `FLOW.md` for full system architecture detail.

---

## Hardware

- Adafruit ESP32 Feather V2
- USB cable (for flashing and serial)
- Must be on the same WiFi network as the Raspberry Pi

---

## Files

### What lives on the board (must be uploaded)

| File | Source in repo |
|---|---|
| `smart_esp_comm.py` | `ESP-Now_Comm_Packet/smart_esp_comm.py` |
| `camera_mesh.py` | `esp32_rpi_bridge/camera_mesh.py` |
| `config.json` | `esp32_rpi_bridge/config.json` (edit first) |
| `peer_file.json` | created automatically during provisioning |

### What you run from Thonny (no upload needed during development)

| File | Purpose |
|---|---|
| `main.py` | boot, WiFi connect, async UDP loop |

> **Why the split?** MicroPython can only import files stored in the board's
> own flash memory. `smart_esp_comm.py` and `camera_mesh.py` are imported by
> `main.py`, so they must be on the board. `main.py` itself can be run
> directly from Thonny without uploading during development.

---

## Setup

### 1. Install Thonny

Download from thonny.org. In **Tools → Options → Interpreter**, select
`MicroPython (ESP32)` and the correct COM port.

### 2. Upload dependencies to the board

In Thonny, open **View → Files** to show the file browser.

On the left panel (your PC), navigate to each file below. Right-click →
**Upload to /**.

- `ESP-Now_Comm_Packet/smart_esp_comm.py`
- `esp32_rpi_bridge/camera_mesh.py`
- `esp32_rpi_bridge/config.json` (after editing — see next step)

### 3. Edit config.json before uploading

```json
{
    "name": "camera_bridge",
    "hop": 1,
    "id": 10
}
```

- `name` — unique human-readable label for this node
- `hop` — distance from the host ESP in hops (1 if directly connected to host)
- `id` — unique 1-byte integer across the whole network (1–255, never 0)

Adjust `hop` and `id` to match your network layout before uploading.

### 4. Edit main.py — set WiFi credentials

Open `esp32_rpi_bridge/main.py` and update:

```python
WIFI_SSID     = "your_network"
WIFI_PASSWORD = "your_password"
```

### 5. Run main.py

In Thonny, open `esp32_rpi_bridge/main.py` and press **Run (F5)**.

Expected output:
```
[WiFi] Connecting to your_network ...
[WiFi] Connected — 192.168.x.x
[BOOT] Node ready.
[UDP] Listening on port 5005
```

> **Note the IP address printed on the `[WiFi] Connected` line.**
> You need to enter this IP into `rpi/udp_comm.py` on the Raspberry Pi
> so it knows where to send detection events:
> ```python
> ESP32_IP = "192.168.x.x"   # the IP printed above
> ```
> The ESP32 gets its IP from DHCP, so if it changes after a reboot check
> your router's device list or re-run `main.py` and read the output again.

---

## Provisioning (one-time peer setup)

The mesh uses a peer map stored in `peer_file.json` so nodes know how to
route to each other. You need to tell this node about its neighbors.

**Close Thonny first** — it holds the serial port. Use PuTTY or screen instead
(115200 baud, 8N1). Hard reset the board, then send these commands:

Set this node's identity (if not already done via config.json):
```
SETNAME camera_bridge
SETHOP 1
SETID 10
```

Add each neighbor this node can reach directly:
```
ADD <name> <MAC> <hop> <id> <neighbor_list>
```

Example — adding the host node as a neighbor:
```
ADD host AA:BB:CC:DD:EE:FF 0 1 camera_bridge
```

Push the peer map out to all neighbors:
```
SYNC
```

Verify everything looks right:
```
LIST
```

> `peer_file.json` is created and saved automatically when you run these
> commands. You do not need to create it manually.

---

## Deployment (run on boot without PC)

Once everything is working, upload `main.py` to the board so it starts
automatically on power-on:

1. Thonny → **View → Files**
2. Right-click `main.py` on the left panel → **Upload to /**
3. Hard reset the board — it will now run `main.py` on every boot without
   needing Thonny or a USB connection

---

## Configuration Reference

### main.py

| Variable | Default | Description |
|---|---|---|
| `WIFI_SSID` | — | WiFi network name |
| `WIFI_PASSWORD` | — | WiFi password |
| `LISTEN_PORT` | `5005` | UDP port to receive RPi events on |

### camera_mesh.py

| Variable | Default | Description |
|---|---|---|
| `PERSON_TIMEOUT_S` | `8` | Seconds without a detection before sending CLEAR to mesh |

---

## What the board does at runtime

1. Connects to WiFi (needed to receive UDP from RPi)
2. Initialises ESP-NOW on the same channel as the WiFi AP
3. Loads node identity (`config.json`) and peer map (`peer_file.json`)
4. Listens on UDP port 5005 for person detection events from the RPi
5. On first person detection → sends `"CAM:PERSON:<confidence>"` toward host via mesh
6. While person is still detected → refreshes timer, no further mesh TX
7. After 8 seconds with no detection → sends `"CAM:CLEAR"` toward host via mesh

Motion events from the RPi are intentionally ignored — only AI-confirmed
person classifications are forwarded to the mesh.
