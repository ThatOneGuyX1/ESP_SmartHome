from machine import Pin
import neopixel
import network
import espnow
import json
import time
import urandom

# =======================
# NEOPIXEL SETUP
# =======================
neo_power = Pin(20, Pin.OUT)
neo_power.value(1)

np = neopixel.NeoPixel(Pin(9), 1)

def set_led(r, g, b):
    np[0] = (r, g, b)
    np.write()

# =======================
# GLOBALS
# =======================
PEER_FILE = "peer_file.json"

espnow_instance = None
mac_local = None

recv_queue = []

SEEN_PACKETS = {}
NEIGHBORS = {}
ROUTE_TABLE = {}

HOST_MAC = b'\x34\xB4\x72\x70\x26\x74'

BROADCAST_MAC = b'\xff\xff\xff\xff\xff\xff'

# =========================
# ACTION TYPES
# =========================
ACT_HELLO = 0x01
ACT_PING = 0x02
ACT_ROUTE = 0x20
ACT_FORWARD = 0x30
ACT_STRONGEST = 0xD1

# =========================
# PACKET CREATION
# =========================
def create_msg_packet(
    dest,
    send,
    message,
    health,
    path=None,
    ttl=5,
    act=0xC0
):

    msg_bytes = message.encode()

    if len(msg_bytes) > 180:
        msg_bytes = msg_bytes[:180]

    if path is None:
        path = []

    packet = bytearray()

    packet += dest
    packet += send

    packet += bytes([act])
    packet += bytes([health.get("bat", 0)])

    timestamp = time.ticks_ms() & 0xFFFFFFFF
    packet += timestamp.to_bytes(4, 'big')

    packet_id = urandom.getrandbits(16)
    packet += packet_id.to_bytes(2, 'big')

    packet += bytes([ttl])

    packet += bytes([len(path)])

    for node in path:
        packet += node

    packet += bytes([len(msg_bytes)])
    packet += msg_bytes

    return packet

# =========================
# PACKET PARSING
# =========================
def parse_msg_packet(packet: bytes):

    try:
        dest = bytes(packet[0:6])
        sender = bytes(packet[6:12])

        act = packet[12]
        battery = packet[13]

        timestamp = int.from_bytes(packet[14:18], 'big')

        packet_id = int.from_bytes(packet[18:20], 'big')

        ttl = packet[20]

        path_len = packet[21]

        idx = 22

        path = []

        for _ in range(path_len):
            path.append(bytes(packet[idx:idx+6]))
            idx += 6

        msg_len = packet[idx]
        idx += 1

        msg = packet[idx:idx+msg_len].decode()

        return {
            "destination": dest,
            "sender": sender,
            "action": act,
            "battery": battery,
            "timestamp": timestamp,
            "packet_id": packet_id,
            "ttl": ttl,
            "path": path,
            "message": msg
        }

    except Exception as e:
        print("[PARSE ERROR]", e)
        return None

# =========================
# ESP-NOW SETUP
# =========================
def espnow_setup():

    global espnow_instance
    global mac_local

    sta = network.WLAN(network.WLAN.IF_STA)

    sta.active(True)
    sta.disconnect()

    sta.config(channel=6)

    mac_local = sta.config('mac')

    e = espnow.ESPNow()
    e.active(True)

    e.add_peer(BROADCAST_MAC)

    espnow_instance = e

    print(f"[ESP-NOW] MAC: {format_mac(mac_local)}")

    return espnow_instance

def get_espnow():
    return espnow_instance

def get_local_mac():
    return mac_local

# =========================
# SEND / RECEIVE
# =========================
def espnow_send(peer_mac, packet):

    e = get_espnow()

    try:
        e.send(peer_mac, packet)

    except OSError as err:
        print("[SEND FAIL]", err)

def espnow_add_peer(mac):

    e = get_espnow()

    try:
        e.add_peer(mac)

    except:
        pass

def espnow_set_recv_callback():

    e = get_espnow()

    def _internal_callback(_):

        result = e.irecv(0)

        if result:
            recv_queue.append(result)

    e.irq(_internal_callback)

def get_next_packet():

    if recv_queue:
        return recv_queue.pop(0)

    return None

# =========================
# ROUTING
# =========================
def update_route(destination, next_hop, cost):

    ROUTE_TABLE[destination] = {
        "next_hop": next_hop,
        "cost": cost,
        "last_seen": time.ticks_ms()
    }

def get_best_route(destination):

    if destination in ROUTE_TABLE:
        return ROUTE_TABLE[destination]

    return None

# =========================
# DUPLICATE PROTECTION
# =========================
def packet_seen(sender, packet_id):

    key = (sender, packet_id)

    if key in SEEN_PACKETS:
        return True

    SEEN_PACKETS[key] = time.ticks_ms()

    return False

def cleanup_seen_packets():

    now = time.ticks_ms()

    remove = []

    for key, ts in SEEN_PACKETS.items():

        if time.ticks_diff(now, ts) > 30000:
            remove.append(key)

    for key in remove:
        del SEEN_PACKETS[key]

# =========================
# UTIL
# =========================
def format_mac(mac: bytes):

    return ':'.join(f'{b:02X}' for b in mac)


# =======================
# LED COLORS
# =======================

CURRENT_LED = None


def _set_state(color_tuple):
    global CURRENT_LED

    if CURRENT_LED != color_tuple:
        CURRENT_LED = color_tuple
        set_led(*color_tuple)


def led_booting():
    _set_state((0, 0, 255))


def led_direct_host():
    _set_state((0, 255, 0))


def led_relay_route():
    _set_state((0, 255, 255))


def led_searching():
    _set_state((255, 255, 0))


def led_forwarding():
    set_led(180, 0, 255)


def led_weak():
    _set_state((255, 0, 0))


def led_disconnected():
    _set_state((0, 0, 0))