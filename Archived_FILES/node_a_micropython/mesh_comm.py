"""
ESP-NOW Mesh Communication Layer.
Mirrors mesh_comm.c from the C firmware.

Uses MicroPython's built-in espnow module (v1.20+).
Supports both synchronous (deep-sleep one-shot) and async (always-on) modes.
"""
import network
import espnow
import time

import Archived_FILES.node_a_micropython.config as config
import Archived_FILES.node_a_micropython.message as message


class MeshComm:
    def __init__(self, channel=None):
        self.channel = channel or config.ESPNOW_CHANNEL
        self._espnow = None
        self._sta = None
        self._own_mac = b'\x00' * 6
        self._seq = 0
        self._last_rssi = 0
        self._recv_cb = None

    def init(self):
        """Initialize WiFi STA + ESP-NOW. Call once on boot."""
        # WiFi STA mode (ESP-NOW needs it active, no AP connection)
        self._sta = network.WLAN(network.STA_IF)
        self._sta.active(True)
        self._sta.config(channel=self.channel)

        self._own_mac = self._sta.config('mac')
        print('[MESH] Node MAC:', config.mac_to_str(self._own_mac))

        # Initialize ESP-NOW
        self._espnow = espnow.ESPNow()
        self._espnow.active(True)

        # Add broadcast and gateway peers
        try:
            self._espnow.add_peer(config.BROADCAST_MAC)
        except OSError:
            pass  # already added
        try:
            self._espnow.add_peer(config.GATEWAY_MAC)
        except OSError:
            pass

        print('[MESH] ESP-NOW initialized on channel', self.channel)

    def add_peer(self, mac):
        """Add an ESP-NOW peer."""
        try:
            self._espnow.add_peer(mac)
        except OSError:
            pass  # already exists

    def get_own_mac(self):
        return self._own_mac

    def get_last_rssi(self):
        return self._last_rssi

    def register_recv_cb(self, cb):
        """Register a callback: cb(frame_dict) called on valid received frames."""
        self._recv_cb = cb

    def send(self, dst_mac, msg_type, payload, ttl=0):
        """Build and send a frame. Returns True on success."""
        if ttl == 0:
            ttl = config.MESH_DEFAULT_TTL

        self._seq = (self._seq + 1) & 0xFFFF
        timestamp = config.get_uptime_ms()

        buf = message.serialize(
            self._own_mac, dst_mac, msg_type,
            self._seq, ttl, timestamp, payload
        )
        if buf is None:
            print('[MESH] Serialize failed')
            return False

        # Determine next hop (default: gateway for unicast, broadcast as-is)
        next_hop = dst_mac if dst_mac == config.BROADCAST_MAC else config.GATEWAY_MAC

        # Send with retry
        for attempt in range(config.MESH_MAX_RETRIES):
            try:
                ok = self._espnow.send(next_hop, buf, True)
                if ok:
                    return True
            except OSError as e:
                print('[MESH] TX attempt %d error: %s' % (attempt + 1, e))
            time.sleep_ms(config.MESH_RETRY_DELAY_MS)

        print('[MESH] TX FAILED to', config.mac_to_str(next_hop),
              'type=0x%02X after %d attempts' % (msg_type, config.MESH_MAX_RETRIES))
        return False

    def recv(self, timeout_ms=1000):
        """Blocking receive. Returns frame dict or None."""
        try:
            mac, data = self._espnow.recv(timeout_ms)
        except OSError:
            return None

        if data is None:
            return None

        if not message.validate(data):
            print('[MESH] Invalid frame received (bad CRC or TTL)')
            return None

        frame = message.deserialize(data)
        if frame is None:
            return None

        print('[MESH] RX from', config.mac_to_str(frame['src_mac']),
              'type=0x%02X seq=%u len=%u' % (
                  frame['msg_type'], frame['sequence_num'], frame['payload_len']))

        if self._recv_cb:
            self._recv_cb(frame)

        return frame

    async def recv_loop(self):
        """Async receive loop for always-on mode. Dispatches to registered callback."""
        import uasyncio as asyncio

        while True:
            try:
                mac, data = self._espnow.recv(0)  # non-blocking
                if data is not None and message.validate(data):
                    frame = message.deserialize(data)
                    if frame and self._recv_cb:
                        self._recv_cb(frame)
            except OSError:
                pass
            await asyncio.sleep_ms(50)
