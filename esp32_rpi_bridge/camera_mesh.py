"""
camera_mesh.py — Bridge layer: RPi person detections → ESP-NOW mesh alerts.

Sits between the UDP receiver (main.py) and the mesh network (message.py).
Implements a state machine so only state *transitions* generate mesh traffic,
not every individual camera frame.

State machine:
    CLEAR ──(person detected)──► PERSON  → sends ALERT_PERSON_DETECTED
    PERSON ──(timeout expires)──► CLEAR  → sends ALERT_PERSON_CLEARED
    PERSON ──(more detections)──► PERSON → refreshes timer, no TX

This mirrors the PIR occupancy debounce in sensor_task.py.

Dependencies (copy from node_a_micropython onto the board):
    message.py

Alert codes (camera-specific extension — gateway must handle 0x20/0x21):
    0x20  ALERT_PERSON_DETECTED  — person appeared; sensor_reading = confidence * 100
    0x21  ALERT_PERSON_CLEARED   — person gone;     sensor_reading = 0
"""

import network
import espnow
import time
import message

# ---------------------------------------------------------------------------
# Config — update GATEWAY_MAC to match your gateway node
# ---------------------------------------------------------------------------
GATEWAY_MAC    = b'\xc0\xcd\xd6\x35\xc9\x98'   # must match config.py on other nodes
BROADCAST_MAC  = b'\xff\xff\xff\xff\xff\xff'

DEFAULT_TTL    = 5
MAX_RETRIES    = 3
RETRY_DELAY_MS = 100

# How long (seconds) with no detection before declaring the person gone.
# Too short → flickers on missed frames. Too long → gateway stays alert too long.
# 8s is safe at 5 FPS even if the model misses a few frames in a row.
PERSON_TIMEOUT_S = 8
# ---------------------------------------------------------------------------

ALERT_PERSON_DETECTED = 0x20
ALERT_PERSON_CLEARED  = 0x21


class CameraMesh:

    def __init__(self):
        self._en       = None
        self._src_mac  = None
        self._seq      = 0
        self._state    = 'clear'   # 'clear' | 'person'
        self._last_seen = 0

    def init(self):
        """Initialise ESP-NOW. Must be called AFTER WiFi is connected to AP.

        We do NOT call MeshComm.init() because that tries to set the WiFi
        channel manually, which fails when STA is already joined to an AP.
        ESP-NOW will automatically use the AP's channel, which is correct.
        """
        sta = network.WLAN(network.STA_IF)
        self._src_mac = sta.config('mac')

        self._en = espnow.ESPNow()
        self._en.active(True)

        for mac in (GATEWAY_MAC, BROADCAST_MAC):
            try:
                self._en.add_peer(mac)
            except OSError:
                pass   # already registered

        print('[MESH] Camera node MAC:', ':'.join('%02X' % b for b in self._src_mac))
        print('[MESH] Gateway MAC:    ', ':'.join('%02X' % b for b in GATEWAY_MAC))
        print('[MESH] ESP-NOW ready')

    # ------------------------------------------------------------------
    # Public API — called by main.py on UDP events
    # ------------------------------------------------------------------

    def on_person(self, confidence: float):
        """Call when RPi reports a person detection.

        Only transmits on CLEAR→PERSON transition; subsequent detections
        while already in PERSON state just refresh the timeout timer.
        """
        self._last_seen = time.time()

        if self._state == 'clear':
            self._state = 'person'
            # confidence → uint16 (e.g. 0.87 → 87)
            conf_int = min(int(confidence * 100), 9999)
            payload = message.pack_alert(ALERT_PERSON_DETECTED, conf_int)
            self._send(payload)
            print('[MESH] PERSON_DETECTED → gateway (conf=%.2f)' % confidence)
        # else: already in 'person' state, timeout refreshed, no TX

    def check_timeout(self):
        """Call periodically (every ~1 s). Handles PERSON→CLEAR transition.

        Returns True if the state just transitioned to clear.
        """
        if self._state == 'person':
            elapsed = time.time() - self._last_seen
            if elapsed >= PERSON_TIMEOUT_S:
                self._state = 'clear'
                payload = message.pack_alert(ALERT_PERSON_CLEARED, 0)
                self._send(payload)
                print('[MESH] PERSON_CLEARED → gateway (%ds timeout)' % PERSON_TIMEOUT_S)
                return True
        return False

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _send(self, payload: bytes):
        self._seq = (self._seq + 1) & 0xFFFF
        ts = time.ticks_ms() & 0xFFFFFFFF

        buf = message.serialize(
            self._src_mac, GATEWAY_MAC,
            message.MSG_TYPE_ALERT,
            self._seq, DEFAULT_TTL, ts, payload
        )
        if buf is None:
            print('[MESH] Serialize failed — payload too large?')
            return

        for attempt in range(MAX_RETRIES):
            try:
                if self._en.send(GATEWAY_MAC, buf, True):
                    return
            except OSError as e:
                print('[MESH] TX attempt %d error: %s' % (attempt + 1, e))
            time.sleep_ms(RETRY_DELAY_MS)

        print('[MESH] TX FAILED after %d attempts' % MAX_RETRIES)
