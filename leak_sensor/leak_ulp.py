"""
leak_ulp.py — Timer-based deep sleep leak sensor for ESP32 Feather V2.

The ESP32 wakes every POLL_INTERVAL_S, reads the ADC, and goes back to
deep sleep (~10 µA) if dry. On a leak it connects WiFi, fires a UDP
alert, and sleeps again. No extra libraries needed.

Hardware:
    Leak sensor analog out → any analog pin (A0-A5)
    Default: A0 = GPIO26
"""

import machine
import network
import socket
import json
import time

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
POLL_INTERVAL_S  = 5          # wake and check ADC every N seconds
LEAK_THRESHOLD   = 1000       # ADC 0-4095; run leak_sensor.py first to calibrate
ALERT_HOLDOFF_S  = 30         # seconds to wait between repeated alerts on a sustained leak

ALERT_IP   = "10.254.250.41"   # destination for UDP leak alerts
ALERT_PORT = 5007

WIFI_SSID     = "YOUR_SSID"
WIFI_PASSWORD = "YOUR_PASSWORD"
# ---------------------------------------------------------------------------

adc = machine.ADC(machine.Pin(26))   # A0; change to 25/34/39/36/4 for A1-A5
adc.atten(machine.ADC.ATTN_11DB)     # full 0-3.3 V range

# ---------------------------------------------------------------------------
# Networking
# ---------------------------------------------------------------------------
def connect_wifi():
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    if sta.isconnected():
        return sta
    sta.connect(WIFI_SSID, WIFI_PASSWORD)
    deadline = time.time() + 15
    while not sta.isconnected():
        if time.time() > deadline:
            raise RuntimeError("[WiFi] Timed out")
        time.sleep(0.5)
    print("[WiFi] Connected:", sta.ifconfig()[0])
    return sta

def send_alert(val):
    connect_wifi()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    msg = json.dumps({"event": "leak", "adc": val, "ts": int(time.time())}).encode()
    sock.sendto(msg, (ALERT_IP, ALERT_PORT))
    sock.close()
    print(f"[ALERT] Sent  adc={val}  → {ALERT_IP}:{ALERT_PORT}")

# ---------------------------------------------------------------------------
# Main — runs on every wake from deep sleep
# ---------------------------------------------------------------------------
val = adc.read()
print(f"[WAKE] ADC={val}  threshold={LEAK_THRESHOLD}")

if val >= LEAK_THRESHOLD:
    print("[LEAK] Detected!")
    try:
        send_alert(val)
    except Exception as e:
        print(f"[ALERT] Failed: {e}")
    # Hold longer before next sleep so we don't spam on a sustained leak
    machine.deepsleep(ALERT_HOLDOFF_S * 1000)
else:
    machine.deepsleep(POLL_INTERVAL_S * 1000)
