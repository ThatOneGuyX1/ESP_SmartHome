# Raspberry Pi Node — Setup Guide

Camera-based motion and person detection node for the ESP SmartHome mesh.  
Runs `detection_v2.py` and communicates with the ESP32 gateway over UDP.

---

## Hardware Requirements

- Raspberry Pi (any model with a CSI camera port — Pi 3B, 3B+, 4B, or 5)
- Raspberry Pi Camera Module (v1, v2, or v3) — connected to the CSI ribbon cable port
- MicroSD card (16 GB+ recommended)
- Power supply appropriate for your Pi model

> **Pi 3 users:** The Pi 3 is noticeably slower running the AI model. The code already limits the camera to 5 FPS to keep it stable. Expect ~1–2 second inference latency.

---

## 1. Flash Pi OS (Headless Setup)

Use **Raspberry Pi Imager** (download at raspberrypi.com/software).

1. **Choose Device** → select your Pi model
2. **Choose OS** → Raspberry Pi OS (64-bit) — use the full version, not Lite
3. **Choose Storage** → select your SD card
4. Click the **gear icon (⚙)** before writing to pre-configure:
   - Set hostname (e.g. `smartpi`)
   - Enable SSH → **Use password authentication**
   - Set username and password (e.g. user: `pi`)
   - Configure wireless LAN → enter your WiFi SSID and password
   - Set locale/timezone
5. Click **Write**

> This eliminates the need to connect a monitor or keyboard. The Pi will connect to WiFi and have SSH enabled on first boot.

---

## 2. First Boot & SSH In

1. Insert the SD card and power on the Pi
2. Wait ~60–90 seconds for first boot to complete
3. Find the Pi's IP address:
   - Check your router's connected devices list, **or**
   - If you have another terminal on the same network: `ping smartpi.local`
4. SSH in:
   ```bash
   ssh pi@<pi-ip-address>
   ```
   Or by hostname:
   ```bash
   ssh pi@smartpi.local
   ```

---

## 3. Enable & Test the Camera

The camera should be enabled by default on Pi OS Bookworm. Test it:

```bash
rpicam-hello -t 0 --qt-preview
```

If that opens a preview window, the camera is working. Close it with `Ctrl+C`.

**Pi 3 / older Pi OS only** — if `rpicam-hello` is not found, enable the camera first:
```bash
sudo raspi-config
# Interface Options → Camera → Enable → reboot
```

**Lower resolution preview** (useful on Pi 3 to check without lag):
```bash
rpicam-hello -t 0 --width 640 --height 480 --framerate 15 --qt-preview
```

---

## 4. Set Up Git & Clone the Repo

Install git (usually pre-installed, but just in case):
```bash
sudo apt update && sudo apt install -y git
```

Configure your identity:
```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

Clone the repo:
```bash
cd ~
git clone <your-repo-url> ESP_SmartHome
cd ESP_SmartHome
```

The `rpi/model/` directory with `deploy.prototxt` and `mobilenet_iter_73000.caffemodel` is already committed — no manual model download needed.

---

## 5. Python Environment & Dependencies

Create and activate a virtual environment:
```bash
cd ~/ESP_SmartHome/rpi
python3 -m venv env
source env/bin/activate
```

Install dependencies:
```bash
pip install opencv-python-headless numpy
```

> Use `opencv-python-headless` — it skips GUI libraries you don't need on a headless Pi and installs much faster.

**Pi OS Bookworm only** — if pip refuses with "externally managed environment":
```bash
pip install opencv-python-headless numpy --break-system-packages
```
In that case you can skip the venv and install system-wide.

Verify OpenCV installed correctly:
```bash
python3 -c "import cv2; print(cv2.__version__)"
```

---

## 6. Configure UDP Communication

Open `udp_comm.py` and set the ESP32's IP address:
```bash
nano udp_comm.py
```

Update line 26:
```python
ESP32_IP = "192.168.x.x"   # replace with your ESP32 Feather V2's actual IP
```

> The ESP32's IP is printed to its serial monitor on boot: `[WiFi] Connected — IP: x.x.x.x`

---

## 7. Test the UDP Link

With the ESP32 running its firmware, test the link from the Pi:
```bash
source env/bin/activate   # if using venv
python3 udp_comm.py
```

You should see `[UDP] Sent` on the Pi and the events printed on the ESP32 serial monitor.

---

## 8. Run the Detection System

```bash
source env/bin/activate   # if using venv
python3 detection_v2.py
```

Expected output:
```
Loading AI model from .../model/mobilenet_iter_73000.caffemodel...
[UDP] Comm ready — sending to 192.168.x.x:5005, listening on :6006
System Live: Monitoring...
Status: Scanning...
[UDP] Sent: {'event': 'motion', ...}
!!! PERSON DETECTED (0.87)
[UDP] Sent: {'event': 'person', 'confidence': 0.87, ...}
```

Stop with `Ctrl+C`.

---

## 9. (Optional) Run on Boot

To start detection automatically when the Pi powers on:
```bash
sudo nano /etc/systemd/system/smartcam.service
```

Paste:
```ini
[Unit]
Description=SmartHome Camera Detection
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/ESP_SmartHome/rpi
ExecStart=/home/pi/ESP_SmartHome/rpi/env/bin/python3 detection_v2.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Enable it:
```bash
sudo systemctl enable smartcam
sudo systemctl start smartcam
sudo systemctl status smartcam   # verify it's running
```

---

## Find Pi IP Address (if needed later)

```bash
ip -4 addr
```

The address on `wlan0` is your WiFi IP.

---

## File Structure

```
rpi/
├── detection_v2.py       # main detection loop
├── udp_comm.py           # UDP communication with ESP32
└── model/
    ├── deploy.prototxt           # MobileNet SSD network definition
    └── mobilenet_iter_73000.caffemodel   # pretrained weights
```
