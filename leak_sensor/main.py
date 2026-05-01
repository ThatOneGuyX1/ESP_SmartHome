"""
main.py — Leak sensor node for ESP32 Feather V2.

Wakes every POLL_INTERVAL_S, reads the ADC, and goes back to deep sleep
if dry (~10 µA idle). On a leak it sends an ACT_REPORT_HOME alert toward
the host via the ESP-NOW mesh, then sleeps for ALERT_HOLDOFF_S.

Because this node deep-sleeps, main.py runs from scratch on every wake.
smart_esp_comm is only initialised when a leak is detected, keeping the
dry-cycle wake time under 100ms.

Files required on board:
    main.py             (this file)
    smart_esp_comm.py   (copy from ESP-Now_Comm_Packet/)
    config.json         (this node's name/hop/id)
    peer_file.json      (built during provisioning)

Hardware:
    Leak sensor analog out → A0 (GPIO26)
    Change pin below if using a different analog input.
"""

import machine
import time
import smart_esp_comm as sh

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
POLL_INTERVAL_S = 5      # seconds between dry checks
ALERT_HOLDOFF_S = 30     # seconds between repeated alerts on sustained leak
LEAK_THRESHOLD  = 1000   # ADC 0-4095 — run leak_sensor.py first to calibrate
# ---------------------------------------------------------------------------

adc = machine.ADC(machine.Pin(26))  # A0=26, A1=25, A2=34, A3=39, A4=36, A5=4
adc.atten(machine.ADC.ATTN_11DB)    # full 0-3.3V range

val = adc.read()
print("[WAKE] ADC=%d  threshold=%d" % (val, LEAK_THRESHOLD))

if val >= LEAK_THRESHOLD:
    print("[LEAK] Detected — alerting mesh")
    try:
        # Init ESP-NOW — no WiFi AP needed, ESP-NOW is peer-to-peer
        sh.espnow_setup()
        sh.load_config()
        sh.load_peers()

        next_hop = sh._find_next_hop_toward_home()
        if next_hop:
            # Find host MAC (hop 0) from peer map
            host_mac = sh.BROADCAST_MAC
            for entry in sh.PEER_DICT.values():
                if entry.get("hop", 999) == 0:
                    host_mac = sh.mac_bytes(entry["mac"])
                    break

            msg = ("LEAK:%d" % val).encode()
            pkt = sh.create_msg_packet(
                dest_mac=host_mac,
                action=sh.ACT_REPORT_HOME,
                message=msg,
                health=None,
                trail=[]
            )
            sh.espnow_send(next_hop, pkt)
            print("[MESH] Alert sent: LEAK:%d" % val)
        else:
            print("[MESH] No route to host — not provisioned yet?")

    except Exception as e:
        print("[MESH] Failed: %s" % e)

    machine.deepsleep(ALERT_HOLDOFF_S * 1000)

else:
    print("[DRY] Sleeping %ds" % POLL_INTERVAL_S)
    machine.deepsleep(POLL_INTERVAL_S * 1000)
