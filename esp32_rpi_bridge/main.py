"""
main.py — ESP32 Feather V2 UDP receiver for RPi camera/detection node.
Flash this file as main.py. It connects to WiFi, listens for detection
events from the RPi on UDP port 5005, and sends ACKs back on port 5006.

TODO: forward events into the mesh network once that layer is wired up.
"""

import network
import socket
import json
import time

# ---------------------------------------------------------------------------
# CONFIG — update these before flashing
# ---------------------------------------------------------------------------
WIFI_SSID     = "YOUR_SSID"
WIFI_PASSWORD = "YOUR_PASSWORD"

LISTEN_PORT   = 5005   # must match ESP32_PORT in rpi/udp_comm.py
RPI_PORT      = 5006   # must match LISTEN_PORT in rpi/udp_comm.py
# ---------------------------------------------------------------------------


def connect_wifi(ssid, password, timeout_s=15):
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    if sta.isconnected():
        print("[WiFi] Already connected:", sta.ifconfig()[0])
        return sta
    print(f"[WiFi] Connecting to {ssid} ...")
    sta.connect(ssid, password)
    deadline = time.time() + timeout_s
    while not sta.isconnected():
        if time.time() > deadline:
            raise RuntimeError("[WiFi] Connection timed out")
        time.sleep(0.5)
    print("[WiFi] Connected — IP:", sta.ifconfig()[0])
    return sta


def handle_event(msg: dict, rpi_addr: tuple, sock):
    event = msg.get("event")

    if event == "motion":
        print("[EVENT] Motion detected")
        # TODO: forward motion alert into mesh network

    elif event == "person":
        conf = msg.get("confidence", 0.0)
        print(f"[EVENT] PERSON detected  confidence={conf:.2f}")
        # TODO: forward person alert into mesh network

    elif event == "clear":
        print("[EVENT] Scene clear")
        # TODO: forward clear status into mesh network

    else:
        print(f"[EVENT] Unknown event: {msg}")

    # Send ACK back to RPi
    ack = json.dumps({"ack": "ok", "event": event})
    sock.sendto(ack.encode(), rpi_addr)


def main():
    connect_wifi(WIFI_SSID, WIFI_PASSWORD)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", LISTEN_PORT))
    print(f"[UDP] Listening on port {LISTEN_PORT} ...")

    while True:
        try:
            data, addr = sock.recvfrom(256)
            msg = json.loads(data.decode("utf-8"))
            handle_event(msg, addr, sock)
        except ValueError:
            print(f"[UDP] Bad JSON from {addr}, ignoring")
        except Exception as e:
            print(f"[UDP] Error: {e}")


main()
