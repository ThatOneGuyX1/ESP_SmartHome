"""
main.py — ESP32 Feather V2 camera bridge node.

Boot sequence:
  1. Connect to WiFi AP (needed for UDP from RPi)
  2. smart_esp_comm.boot() — loads identity/peers, starts ESP-NOW on same channel
  3. Two async tasks:
       udp_loop     — receives person events from RPi, forwards to mesh
       timeout_loop — fires PERSON_CLEARED when person gone > 8s

Files required on board:
    main.py
    camera_mesh.py
    smart_esp_comm.py    (copy from ESP-Now_Comm_Packet/)
    config.json          (this node's name/hop/id)
    peer_file.json       (built during provisioning via serial commands)
"""

import network
import socket
import json
import time
import uasyncio as asyncio
import smart_esp_comm as sh
import camera_mesh

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
WIFI_SSID     = ""
WIFI_PASSWORD = ""
LISTEN_PORT   = 5005
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
            raise RuntimeError("[WiFi] Timed out")
        time.sleep(0.5)
    print("[WiFi] Connected —", sta.ifconfig()[0])


async def udp_loop(sock):
    while True:
        try:
            data, addr = sock.recvfrom(256)
            msg = json.loads(data.decode())
            event = msg.get("event")

            if event == "person":
                conf = msg.get("confidence", 0.0)
                camera_mesh.on_person(conf)
                ack = json.dumps({"ack": "ok", "event": "person"}).encode()
                sock.sendto(ack, addr)

            # motion and clear ignored — mesh clear driven by camera_mesh timeout

        except OSError:
            pass
        except ValueError:
            print("[UDP] Bad JSON, ignoring")

        await asyncio.sleep_ms(50)


async def timeout_loop():
    while True:
        camera_mesh.check_timeout()
        await asyncio.sleep_ms(1000)


async def main():
    # WiFi must come before sh.boot() so ESP-NOW adopts the AP's channel
    connect_wifi()

    sh.boot()   # loads config.json + peer_file.json, starts ESP-NOW, registers recv CB

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", LISTEN_PORT))
    sock.setblocking(False)
    print("[UDP] Listening on port", LISTEN_PORT)

    await asyncio.gather(
        udp_loop(sock),
        timeout_loop(),
    )


asyncio.run(main())
