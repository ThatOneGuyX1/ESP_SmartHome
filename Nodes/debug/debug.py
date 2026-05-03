"""
main.py — ESP-NOW hardware diagnostic for leak sensor node.

Bypasses smart_esp_comm entirely to rule out config/peer file issues.
Prints its own MAC, registers the host MAC manually, and sends a raw
ping every 5 seconds. Also prints anything it receives.

BEFORE FLASHING:
    Replace HOST_MAC below with the host ESP32's actual MAC.
"""

import network
import espnow
import time

HOST_MAC = b'\x00\x4B\x12\xBE\x27\x28'  # ← replace with host MAC e.g. b'\xAA\xBB\xCC\xDD\xEE\xFF'

# ── Init WLAN + ESP-NOW ───────────────────────────────────────────────────────
sta = network.WLAN(network.WLAN.IF_STA)
sta.active(True)
sta.disconnect()
sta.config(channel=6)

print("[DIAG] Channel: %d" % sta.config('channel'))

my_mac = sta.config('mac')
print("[DIAG] My MAC: %s" % ':'.join('%02X' % b for b in my_mac))
print("[DIAG] Channel: %d" % sta.config('channel'))

e = espnow.ESPNow()
e.active(True)

# Register host as a peer
try:
    e.add_peer(HOST_MAC)
    print("[DIAG] Host peer registered: %s" % ':'.join('%02X' % b for b in HOST_MAC))
except OSError as err:
    print("[DIAG] add_peer failed: %s" % err)

print("[DIAG] Starting send/receive loop...")

cycle = 0
while True:
    cycle += 1

    # ── Send ─────────────────────────────────────────────────────────────────
    try:
        e.send(HOST_MAC, b'PING:%d' % cycle)
        print("[TX] Sent PING:%d" % cycle)
    except OSError as err:
        print("[TX] Send failed: %s" % err)

    # ── Receive (non-blocking poll) ───────────────────────────────────────────
    mac, msg = e.irecv(0)
    if mac:
        print("[RX] From %s: %s" % (':'.join('%02X' % b for b in mac), msg))
    else:
        print("[RX] Nothing received")

    time.sleep(5)
