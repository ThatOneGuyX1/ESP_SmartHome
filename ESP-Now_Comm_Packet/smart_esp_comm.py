from machine import Pin
import neopixel
import network
import espnow
import json
import time

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

PEER_FILE = "peer_file.json"
PEER_DICT = {}

espnow_instance = None
mac_local = None

recv_queue = []
SEEN_PACKETS = set()

# =========================
# PACKET CREATION
# =========================
def create_msg_packet(dest, send, message, health, path=None, ttl=5, act=0xC0):
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

        ttl = packet[18]

        path_len = packet[19]
        idx = 20

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
    global espnow_instance, mac_local

    sta = network.WLAN(network.WLAN.IF_STA)
    sta.active(True)
    sta.disconnect()
    sta.config(channel=6)

    mac_local = sta.config('mac')

    e = espnow.ESPNow()
    e.active(True)

    BROADCAST_MAC = b'\xff\xff\xff\xff\xff\xff'
    e.add_peer(BROADCAST_MAC)

    espnow_instance = e
    print(f"[ESP-NOW] Ready. Local MAC: {format_mac(mac_local)}")
    return espnow_instance


def get_espnow():
    if espnow_instance is None:
        raise RuntimeError("ESP-NOW not initialized.")
    return espnow_instance


def get_local_mac():
    if mac_local is None:
        raise RuntimeError("ESP-NOW not initialized.")
    return mac_local


# =========================
# SEND / RECEIVE
# =========================
def espnow_send(peer_mac: bytes, packet: bytes):
    e = get_espnow()

    if len(packet) > 250:
        print("[ERROR] Packet too large")
        return

    try:
        e.send(peer_mac, bytes(packet))
    except OSError as err:
        print(f"[ESP-NOW] Send failed: {err}")


def espnow_add_peer(mac: bytes):
    e = get_espnow()
    try:
        e.add_peer(mac)
    except OSError:
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
def choose_best_peer():
    e = get_espnow()

    best_peer = None
    best_score = -9999

    for peer in e.peers_table:
        rssi = e.peers_table[peer][0]

        rssi_score = (rssi + 100)
        score = rssi_score

        if score > best_score:
            best_score = score
            best_peer = peer

    return best_peer

def get_best_rssi_peer():
    e = get_espnow()

    best_peer = None
    best_rssi = -999

    for peer in e.peers_table:
        try:
            rssi = e.peers_table[peer][0]

            # Ignore broadcast MAC
            if peer == b'\xff\xff\xff\xff\xff\xff':
                continue
            
            if rssi > best_rssi:
                best_rssi = rssi
                best_peer = peer

        except:
            pass

    return best_peer, best_rssi

# =========================
# UTIL
# =========================
def format_mac(mac: bytes) -> str:
    return ':'.join(f'{b:02X}' for b in mac)