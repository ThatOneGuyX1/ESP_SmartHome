"""
main.py — ESP32 Feather V2: RPi UDP receiver → ESP-NOW mesh bridge.

Boot sequence:
  1. Connect to WiFi (for UDP from RPi)
  2. Init ESP-NOW mesh layer (camera_mesh.py)
  3. Run two concurrent async tasks:
       udp_loop     — receives RPi events, forwards person detections to mesh
       timeout_loop — triggers PERSON_CLEARED alert when person gone > N seconds

Motion and clear events from the RPi are intentionally ignored here;
the mesh clear is driven by the timeout in camera_mesh.py, not the RPi signal.

Files required on the board:
    main.py         (this file)
    camera_mesh.py
    message.py      (copy from node_a_micropython/)
"""

import network
import socket
import json
import time
import uasyncio as asyncio
from camera_mesh import CameraMesh

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
WIFI_SSID     = "Johanan "
WIFI_PASSWORD = "tortoise123"

LISTEN_PORT   = 5005   # must match ESP32_PORT in rpi/udp_comm.py
# ---------------------------------------------------------------------------


def connect_wifi(timeout_s=15):
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    if sta.isconnected():
        print("[WiFi] Already connected:", sta.ifconfig()[0])
        return
    print("[WiFi] Connecting to", WIFI_SSID, "...")
    sta.connect(WIFI_SSID, WIFI_PASSWORD)
    deadline = time.time() + timeout_s
    while not sta.isconnected():
        if time.time() > deadline:
            raise RuntimeError("[WiFi] Connection timed out")
        time.sleep(0.5)
    print("[WiFi] Connected —", sta.ifconfig()[0])


async def udp_loop(sock, mesh):
    """Receive UDP packets from RPi and route person detections to mesh."""
    while True:
        try:
            data, addr = sock.recvfrom(256)
            msg = json.loads(data.decode())
            event = msg.get("event")

            if event == "person":
                conf = msg.get("confidence", 0.0)
                print("[UDP] Person (%.2f) → mesh" % conf)
                mesh.on_person(conf)
                ack = json.dumps({"ack": "ok", "event": "person"}).encode()
                sock.sendto(ack, addr)

            elif event in ("motion", "clear"):
                pass   # motion not used; clear handled by camera_mesh timeout

        except OSError:
            pass   # non-blocking recv with no data
        except ValueError:
            print("[UDP] Bad JSON, ignoring")

        await asyncio.sleep_ms(50)


async def timeout_loop(mesh):
    """Periodically check whether the person-present timeout has expired."""
    while True:
        mesh.check_timeout()
        await asyncio.sleep_ms(1000)


async def main():
    connect_wifi()

    mesh = CameraMesh()
    mesh.init()   # ESP-NOW init — must come after WiFi connect

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", LISTEN_PORT))
    sock.setblocking(False)
    print("[UDP] Listening on port", LISTEN_PORT)

    await asyncio.gather(
        udp_loop(sock, mesh),
        timeout_loop(mesh),
    )


asyncio.run(main())
