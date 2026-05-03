"""
main.py — Leak sensor node for ESP32 Feather V2.

Polls the ADC every POLL_INTERVAL_S seconds and forwards an
ACT_REPORT_HOME alert through the mesh whenever a leak is detected.

Hardware:
    Leak sensor analog out → A0 (GPIO26)
"""

import machine
import time
import smart_esp_comm as sh

# ---------------------------------------------------------------------------
POLL_INTERVAL_S = 5
LEAK_THRESHOLD  = 1000   # ADC 0-4095 — adjust after calibration
# ---------------------------------------------------------------------------

sh.boot()

adc = machine.ADC(machine.Pin(18))
adc.atten(machine.ADC.ATTN_11DB)

# Resolve host MAC and next hop once at startup
next_hop = sh._find_next_hop_toward_home()
host_mac = next(
    (sh.mac_bytes(e["mac"]) for e in sh.PEER_DICT.values() if e.get("hop") == 0),
    sh.BROADCAST_MAC
)

print("[BOOT] next_hop=%s  host=%s" % (sh.format_mac(next_hop) if next_hop else "None", sh.format_mac(host_mac)))


HOST_MAC = sh.mac_bytes(sh.PEER_DICT["host"]["mac"])

# Initial test ping
test_pkt = sh.create_msg_packet(
    dest_mac = HOST_MAC,
    action   = sh.ACT_TEST,
    message  = b''
)

sh.espnow_send(HOST_MAC, test_pkt)
print("[TEST] Ping sent to light_1")

test_pkt = sh.create_msg_packet(
    dest_mac = host_mac,
    action   = sh.ACT_TEST,
    message  = b'11111111'
)

sh.espnow_send(HOST_MAC, test_pkt)
print("[TEST] Ping sent to Host")




while True:
    if sh.check_request_flag() == True:
        print("[MAIN] Action request received — toggling LED...")
    val  = adc.read()
    leak = val >= LEAK_THRESHOLD
    print("[ADC] %d — %s" % (val, "LEAK" if leak else "dry"))

    if leak and next_hop:
        pkt = sh.create_msg_packet(
            dest_mac = host_mac,
            action   = (sh.ACT_REPORT_HOME | sh.ACT_REQ_ACTION),
            message  = ("LEAK:%d" % val).encode(),
            trail    = []
        )
        sh.espnow_send(host_mac, pkt)
        print("[MESH] Alert sent")

    time.sleep(POLL_INTERVAL_S)
