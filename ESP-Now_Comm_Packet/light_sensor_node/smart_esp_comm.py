# smart_esp_comm.py
# Lightweight ESP-NOW communication module for ESP8266 light_1 node.
# Adds peer syncing, but keeps host/routing/UART logic removed for memory.

import network
import espnow
import json
import struct
import time

try:
    import config
except ImportError:
    config = None


# ── Files ─────────────────────────────────────────────────

PEER_FILE = "peer_file.json"
CONFIG_FILE = "config.json"

BROADCAST_MAC = b'\xff\xff\xff\xff\xff\xff'


# ── Action bytes ──────────────────────────────────────────

ACT_TEST        = 0x02
ACT_SENSOR_RPT  = 0x01
ACT_REQ_ACTION  = 0x08
ACT_RPT_ACTION  = 0x0C
ACT_REPORT_HOME = 0xC0
ACT_SYNC_PEERS  = 0x50


# ── Packet layout offsets ─────────────────────────────────

PKT_DEST_START   = 0
PKT_DEST_END     = 6
PKT_SENDER_START = 6
PKT_SENDER_END   = 12
PKT_ACTION       = 12
PKT_MSG_LEN      = 13
PKT_MSG_START    = 14
PKT_MSG_END      = 46
PKT_FLAGS        = 46
PKT_HEALTH_START = 47
PKT_HEALTH_END   = 57
PKT_TRAIL_START  = 57
PKT_TRAIL_END    = 67
PKT_TOTAL_SIZE   = 67

MAX_MSG_BYTES   = 32
MAX_TRAIL_HOPS  = 10

FLAG_HEALTH = 0x01


# ── Local state ───────────────────────────────────────────

espnow_instance = None
mac_local = None

PEER_DICT = {}

LOCAL_NAME = None
LOCAL_HOP = 0
LOCAL_ID = None

REQUEST_FLAG = False
_last_sync_hash = None


# ── Basic helpers ─────────────────────────────────────────

def mac_bytes(mac_str):
    return bytes(int(x, 16) for x in mac_str.split(":"))


def format_mac(mac):
    return ":".join("%02X" % b for b in mac)


def get_espnow():
    if espnow_instance is None:
        raise RuntimeError("Call boot() first.")
    return espnow_instance


def check_request_flag():
    return REQUEST_FLAG


def clear_request_flag():
    global REQUEST_FLAG
    REQUEST_FLAG = False


def _get_local_id():
    if LOCAL_ID is None:
        raise RuntimeError("Node ID not set. Check config.json.")
    return LOCAL_ID


def _get_my_neighbors():
    return [
        name for name, entry in PEER_DICT.items()
        if LOCAL_NAME in entry.get("neighbors", [])
    ]


def _espnow_add_peer_safe(mac):
    try:
        get_espnow().add_peer(mac)
    except OSError:
        pass


def _name_for_mac(mac):
    mac_str = format_mac(mac)
    for name, entry in PEER_DICT.items():
        if entry["mac"].upper() == mac_str.upper():
            return name
    return None


def peer_dict_hash():
    raw = json.dumps(PEER_DICT, sort_keys=True)
    h = 5381
    for ch in raw:
        h = ((h << 5) + h + ord(ch)) & 0xFFFFFFFF
    return h


# ── Node Config I/O ───────────────────────────────────────

def load_config():
    global LOCAL_NAME, LOCAL_HOP, LOCAL_ID

    try:
        print("[CONFIG] Loading from", CONFIG_FILE)
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)

        LOCAL_NAME = data["name"]
        LOCAL_HOP = data["hop"]
        LOCAL_ID = data["id"]

        print("[CONFIG] Identity: '%s' | hop %s | ID %s" %
              (LOCAL_NAME, LOCAL_HOP, LOCAL_ID))

    except OSError:
        print("[CONFIG] No config file found. Node identity unknown.")
        LOCAL_NAME = None
        LOCAL_HOP = 0
        LOCAL_ID = None

    except KeyError as e:
        print("[CONFIG] Malformed config, missing key:", e)
        LOCAL_NAME = None
        LOCAL_HOP = 0
        LOCAL_ID = None


def save_config():
    data = {
        "name": LOCAL_NAME,
        "hop": LOCAL_HOP,
        "id": LOCAL_ID
    }

    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f)

    print("[CONFIG] Saved: '%s' | hop %s | ID %s" %
          (LOCAL_NAME, LOCAL_HOP, LOCAL_ID))


# ── Peer File I/O ─────────────────────────────────────────

def save_peers():
    data = {
        "peers": {
            name: {
                "mac": entry["mac"],
                "neighbors": entry["neighbors"],
                "hop": entry["hop"],
                "id": entry["id"]
            }
            for name, entry in PEER_DICT.items()
        }
    }

    with open(PEER_FILE, "w") as f:
        json.dump(data, f)

    print("[PEERS] Saved", len(PEER_DICT), "peers.")


def load_peers():
    global PEER_DICT

    try:
        with open(PEER_FILE, "r") as f:
            data = json.load(f)

    except (OSError, ValueError):
        print("[PEERS] No peer file found or file corrupted, starting fresh.")
        PEER_DICT = {}
        return

    PEER_DICT = data.get("peers", {})

    for name in _get_my_neighbors():
        if name in PEER_DICT:
            _espnow_add_peer_safe(mac_bytes(PEER_DICT[name]["mac"]))

    print("[PEERS] Loaded", len(PEER_DICT), "peers.")


# ── Peer sync ─────────────────────────────────────────────

def _build_sync_packet():
    body = json.dumps({"peers": PEER_DICT})
    packet = bytes([ACT_SYNC_PEERS]) + body.encode()

    if len(packet) > 250:
        print("[SYNC] WARNING: sync packet too large:", len(packet))

    return packet


def sync_peers_outward(exclude_name=None):
    global _last_sync_hash

    payload = _build_sync_packet()
    _last_sync_hash = peer_dict_hash()

    sent_count = 0

    for name in _get_my_neighbors():
        if name == exclude_name:
            continue

        if name not in PEER_DICT:
            continue

        target_mac = mac_bytes(PEER_DICT[name]["mac"])
        espnow_send(target_mac, payload)

        print("[SYNC] Forwarded peer list to", name)
        sent_count += 1

    print("[SYNC] Sync complete -- sent to", sent_count, "neighbor(s).")


def handle_sync_packet(payload, sender_mac=None):
    global PEER_DICT, _last_sync_hash

    try:
        data = json.loads(payload[1:].decode())
    except Exception as e:
        print("[SYNC] Bad sync packet:", e)
        return

    incoming_peers = data.get("peers", {})

    changed = False

    for name, entry in incoming_peers.items():
        if name == LOCAL_NAME:
            continue

        if PEER_DICT.get(name) != entry:
            PEER_DICT[name] = entry
            changed = True

    if not changed:
        print("[SYNC] Peer map already up to date.")
        return

    new_hash = peer_dict_hash()

    if new_hash == _last_sync_hash:
        print("[SYNC] Hash unchanged after merge -- suppressing rebroadcast.")
        return

    for name in _get_my_neighbors():
        if name in PEER_DICT:
            _espnow_add_peer_safe(mac_bytes(PEER_DICT[name]["mac"]))

    save_peers()
    _last_sync_hash = new_hash

    exclude = _name_for_mac(sender_mac) if sender_mac else None

    print("[SYNC] Peer map updated, forwarding outward.")
    sync_peers_outward(exclude_name=exclude)


# ── ESP-NOW setup ─────────────────────────────────────────

def espnow_setup():
    global espnow_instance, mac_local

    try:
        sta = network.WLAN(network.STA_IF)
    except AttributeError:
        sta = network.WLAN(network.WLAN.IF_STA)

    sta.active(True)

    try:
        sta.disconnect()
    except Exception:
        pass

    try:
        ap = network.WLAN(network.AP_IF)
        ap.active(False)
    except Exception:
        pass

    try:
        channel = getattr(config, "ESPNOW_CHANNEL", 6)
        sta.config(channel=channel)
    except Exception:
        pass

    time.sleep_ms(100)

    mac_local = sta.config("mac")

    e = espnow.ESPNow()

    try:
        e.active(False)
    except Exception:
        pass

    e.active(True)

    espnow_instance = e

    print("[ESP-NOW] Ready. MAC:", format_mac(mac_local))

    return e


def boot():
    espnow_setup()
    load_config()
    load_peers()

    try:
        get_espnow().irq(on_receive)
    except Exception:
        pass

    print("[BOOT]", LOCAL_NAME, "ready.")


# ── Packet creation ───────────────────────────────────────

def _encode_health(health):
    # Golden-file compatible health format:
    # Byte 0: temp, Byte 1: battery, Bytes 2-5: uptime, Bytes 6-9: reserved.
    temp = int(health.get("temp", 0))
    temp = max(-128, min(127, temp))

    battery = int(health.get("battery", 0))
    battery = max(0, min(100, battery))

    uptime = int(health.get("uptime", 0)) & 0xFFFFFFFF

    return struct.pack(">bBIxxxx", temp, battery, uptime)


def decode_health(pkt):
    temp, battery, uptime = struct.unpack(
        ">bBI",
        pkt[PKT_HEALTH_START:PKT_HEALTH_START + 6]
    )

    return {
        "temp": temp,
        "battery": battery,
        "uptime": uptime
    }


def _encode_trail(trail=None):
    trail = list(trail) if trail else []

    local_id = _get_local_id()

    if local_id in trail:
        print("[PKT] WARNING: Loop detected -- node ID already in trail:", local_id)

    trail.append(local_id)

    if len(trail) > MAX_TRAIL_HOPS:
        print("[PKT] WARNING: Trail full, packet may be looping.")
        trail = trail[:MAX_TRAIL_HOPS]

    trail_bytes = bytearray(MAX_TRAIL_HOPS)

    for i, node_id in enumerate(trail):
        trail_bytes[i] = int(node_id) & 0xFF

    return bytes(trail_bytes)


def create_msg_packet(dest_mac, action, message=b"", health=None, trail=None):
    if isinstance(message, str):
        message = message.encode("utf-8")

    pkt = bytearray(PKT_TOTAL_SIZE)

    pkt[PKT_DEST_START:PKT_DEST_END] = dest_mac
    pkt[PKT_SENDER_START:PKT_SENDER_END] = mac_local
    pkt[PKT_ACTION] = action

    if len(message) > MAX_MSG_BYTES:
        print("[PKT] Warning: message truncated to", MAX_MSG_BYTES, "bytes.")
        message = message[:MAX_MSG_BYTES]

    pkt[PKT_MSG_LEN] = len(message)
    pkt[PKT_MSG_START:PKT_MSG_START + len(message)] = message

    flags = 0x00

    if health is not None:
        flags |= FLAG_HEALTH

    pkt[PKT_FLAGS] = flags

    if health is not None:
        pkt[PKT_HEALTH_START:PKT_HEALTH_END] = _encode_health(health)

    pkt[PKT_TRAIL_START:PKT_TRAIL_END] = _encode_trail(trail)

    return bytes(pkt)


# ── Send helpers ──────────────────────────────────────────

def espnow_send(peer_mac, packet):
    if len(packet) > 250:
        print("[ERROR] Packet too large:", len(packet))
        return False

    try:
        get_espnow().send(peer_mac, packet)
        return True

    except OSError as err:
        print("[ESP-NOW] Send failed to", format_mac(peer_mac), ":", err)
        return False


def send_to_host(action, message=b"", health=None):
    if "host" not in PEER_DICT:
        print("[ERROR] host not found in peer_file.json")
        return False

    host_mac = mac_bytes(PEER_DICT["host"]["mac"])

    pkt = create_msg_packet(
        dest_mac=host_mac,
        action=action,
        message=message,
        health=health,
        trail=[]
    )

    return espnow_send(host_mac, pkt)


def send_action_report(message=b"OK"):
    return send_to_host(
        action=ACT_RPT_ACTION,
        message=message,
        health=None
    )


# ── Receive/respond to host/sync ──────────────────────────

def on_receive(e):
    global REQUEST_FLAG

    try:
        mac, raw = e.irecv(0)
    except Exception:
        return

    if mac is None or not raw:
        return

    sender_name = _name_for_mac(mac)

    if sender_name is None:
        print("[WARN] Packet from unknown MAC", format_mac(mac), "-- rejected.")
        return

    # Sync packets are not 67-byte normal packets.
    if raw[0] == ACT_SYNC_PEERS:
        handle_sync_packet(raw, sender_mac=mac)
        return

    if len(raw) != PKT_TOTAL_SIZE:
        return

    action = raw[PKT_ACTION]

    if action == ACT_TEST:
        print("[TEST] Ping from", sender_name)
        send_action_report(b"PONG")

    elif action == ACT_REQ_ACTION:
        print("[ACTION] Request from", sender_name)
        REQUEST_FLAG = True
        send_action_report(b"REQ_OK")

