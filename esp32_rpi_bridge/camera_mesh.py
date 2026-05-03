"""
camera_mesh.py — Camera bridge: person detection state machine → ESP-NOW mesh.

Uses smart_esp_comm.py (the new network layer) to route person detection
events toward the host using ACT_REPORT_HOME hop-based routing.

State machine (same logic as before, new transport):
    CLEAR ──(first person packet)──► PERSON → sends "CAM:PERSON:<conf>" toward host
    PERSON ──(more person packets)──► PERSON → refresh timer only, no TX
    PERSON ──(8s no detections)────► CLEAR  → sends "CAM:CLEAR" toward host

Message format (UTF-8, ≤ 32 bytes, decoded by host into JSON):
    "CAM:PERSON:87"   — person detected, confidence = 87%
    "CAM:CLEAR"       — person gone (timeout)

Files required on board:
    smart_esp_comm.py   (copy from ESP-Now_Comm_Packet/)
    config.json         (this node's name, hop, id)
    peer_file.json      (built during provisioning)
"""

import time
import smart_esp_comm as sh

PERSON_TIMEOUT_S = 8   # seconds without a detection before sending CLEAR

_state     = 'clear'   # 'clear' | 'person'
_last_seen = 0


def on_person(confidence: float):
    """Call when RPi reports a confirmed person detection.

    Only transmits on CLEAR→PERSON transition. Subsequent detections
    while already in PERSON state just refresh the timeout timer.
    """
    global _state, _last_seen
    _last_seen = time.time()

    if _state == 'clear':
        _state = 'person'
        conf_int = min(int(confidence * 100), 100)
        _send_toward_home('CAM:PERSON:%d' % conf_int)
        print('[CAM] PERSON_DETECTED → host (conf=%d%%)' % conf_int)
    # else: already in person state, timer refreshed, no TX


def check_timeout():
    """Call periodically (~1s). Fires PERSON→CLEAR transition when timed out."""
    global _state
    if _state == 'person':
        if time.time() - _last_seen >= PERSON_TIMEOUT_S:
            _state = 'clear'
            _send_toward_home('CAM:CLEAR')
            print('[CAM] PERSON_CLEARED → host (%ds timeout)' % PERSON_TIMEOUT_S)


# ── Internals ────────────────────────────────────────────────────────────────

def _find_home_mac():
    """Return MAC bytes of the hop-0 (host) node from PEER_DICT.
    Falls back to broadcast if not yet provisioned."""
    for entry in sh.PEER_DICT.values():
        if entry.get('hop', 999) == 0:
            return sh.mac_bytes(entry['mac'])
    print('[CAM] WARNING: no hop-0 node in peer map, using broadcast')
    return sh.BROADCAST_MAC


def _send_toward_home(message_str: str):
    """Build an ACT_REPORT_HOME packet and send it to the next hop toward host."""
    next_hop_mac = sh._find_next_hop_toward_home()
    if next_hop_mac is None:
        print('[CAM] No route to home — is this node provisioned with neighbors?')
        return

    host_mac  = _find_home_mac()
    msg_bytes = message_str.encode('utf-8')[:sh.MAX_MSG_BYTES]

    pkt = sh.create_msg_packet(
        dest_mac=host_mac,
        action=sh.ACT_REPORT_HOME,
        message=msg_bytes,
        health=None,
        trail=[]
    )
    sh.espnow_send(next_hop_mac, pkt)
    print('[CAM] Packet sent: "%s"' % message_str)
