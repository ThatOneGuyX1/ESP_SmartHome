import network
import espnow
import json
import struct
import sys

# ══════════════════════════════════════════════════════════════════════════════
# PATCH NOTES  (smart_esp_comm.py — patched)
# ──────────────────────────────────────────────────────────────────────────────
#  1. NEW: `_last_sync_hash` module variable + `peer_dict_hash()`
#     DJB2 hash of PEER_DICT to prevent infinite sync loops.
#
#  2. PATCHED: `sync_peers_outward(exclude_name=None)`
#     Now forwards to ALL direct neighbors (up + downstream).
#     Accepts `exclude_name` to skip the sender (anti-pingpong).
#
#  3. PATCHED: `handle_sync_packet(payload, sender_mac=None)`
#     Hash-check prevents infinite rebroadcast.
#     Re-registers new direct neighbors with ESP-NOW before forwarding.
#
#  4. PATCHED: `on_receive(e)`
#     Passes sender MAC into handle_sync_packet().
#
#  5. PATCHED: `handle_serial_command()` — added SYNC and LIST commands.
#
#  6. PATCHED: `parse_packet()` — now includes 'raw' key for forwarding.
#
#  7. COMPLETED: `espnow_setup()`, `load_peers()`, `create_msg_packet()`,
#     `handle_report_home()`, `on_receive()` — all function bodies filled in.
#
#  8. REMOVED: Duplicate stub `create_msg_packet` and duplicate `mac_local`.
# ══════════════════════════════════════════════════════════════════════════════


# ── Constants ─────────────────────────────────────────────────────────────────

PEER_FILE   = "peer_file.json"
CONFIG_FILE = "config.json"

BROADCAST_MAC = b'\xff\xff\xff\xff\xff\xff'

# Action byte flags
ACT_TEST        = 0x02  # 0b0000_0010 — Test comms
ACT_SENSOR_RPT  = 0x01  # 0b0000_0001 — Sensor reporting value
ACT_REQ_ACTION  = 0x08  # 0b0000_1000 — Requesting an action
ACT_RPT_ACTION  = 0x0C  # 0b0000_1100 — Reporting action carried out
ACT_ADD_PEER    = 0x30  # 0b0011_0000 — New peer needs to be added
ACT_REPORT_HOME = 0xC0  # 0b1100_0000 — Forward message toward home
ACT_SYNC_PEERS  = 0x50  # 0b0101_0000 — Full peer map sync

# Packet layout offsets
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

MAX_TRAIL_HOPS  = 10
MAX_MSG_BYTES   = 32

# Flags byte bit masks
FLAG_HEALTH     = 0x01  # 0b0000_0001 — health block present


# ── State ─────────────────────────────────────────────────────────────────────

espnow_instance = None
mac_local       = None

# Full network map: name -> {"mac": str, "neighbors": [str], "hop": int, "id": int}
PEER_DICT  = {}

# This node's own identity, loaded from config.json
LOCAL_NAME = None
LOCAL_HOP  = 0
LOCAL_ID   = None

REQUEST_FLAG = False  # Global flag set by ACT_REQ_ACTION, for main loop to check

# [PATCH] Hash of the last sync we broadcast — prevents infinite sync loops
_last_sync_hash = None


def check_request_flag():
    global REQUEST_FLAG
    return REQUEST_FLAG
# ── ESP-NOW Setup ─────────────────────────────────────────────────────────────

def espnow_setup():
    """Initialize WLAN + ESP-NOW. Call once at boot before anything else."""
    global espnow_instance, mac_local

    
    sta = network.WLAN(network.WLAN.IF_STA)
    sta.active(True)

    sta.disconnect()
    sta.config(channel=6)
    mac_local = sta.config('mac')

    e = espnow.ESPNow()
    try:
        e.active(False)  # tear down any existing session
    except OSError:
        pass
    e.active(True)

    espnow_instance = e
    print(f"[ESP-NOW] Ready. MAC: {format_mac(mac_local)}")
    return e




def get_espnow():
    """Return active ESPNow instance. Raises if espnow_setup() not called."""
    if espnow_instance is None:
        raise RuntimeError("Call espnow_setup() first.")
    return espnow_instance


def espnow_set_recv_callback(callback):
    """
    Register a callback triggered on every incoming message.
    Callback signature: callback(mac: bytes, packet: bytes)
    """
    get_espnow().irq(callback)


def espnow_receive(timeout_ms=0):
    """
    Manually poll for a message. Returns (mac, packet) or (None, None).
    timeout_ms=0 is non-blocking.
    """
    return get_espnow().irecv(timeout_ms)


# ── Node Config I/O ──────────────────────────────────────────────────────────

def load_config():
    """
    Load this node's fixed identity from config.json.
    Sets LOCAL_NAME, LOCAL_HOP, LOCAL_ID.
    """
    global LOCAL_NAME, LOCAL_HOP, LOCAL_ID
    try:
        print(f"[CONFIG] Loading from {CONFIG_FILE}...")
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
        LOCAL_NAME = data["name"]
        LOCAL_HOP  = data["hop"]
        LOCAL_ID   = data["id"]
        print(f"[CONFIG] Identity: '{LOCAL_NAME}' | hop {LOCAL_HOP} | ID {LOCAL_ID}")
    except OSError:
        print("[CONFIG] No config file found. Node identity unknown.")
        LOCAL_NAME = None
        LOCAL_HOP  = 0
        LOCAL_ID   = None
    except KeyError as e:
        print(f"[CONFIG] Malformed config, missing key: {e}")
        LOCAL_NAME = None
        LOCAL_HOP  = 0
        LOCAL_ID   = None


def save_config():
    """Persist this node's identity to config.json."""
    data = {"name": LOCAL_NAME, "hop": LOCAL_HOP, "id": LOCAL_ID}
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f)
    print(f"[CONFIG] Saved: '{LOCAL_NAME}' | hop {LOCAL_HOP} | ID {LOCAL_ID}")


# ── Peer File I/O ────────────────────────────────────────────────────────────

def save_peers():
    """
    Persist PEER_DICT to peer_file.json.
    Only writes known fields -- no runtime-only state bleeds into the file.
    """
    data = {
        "peers": {
            name: {
                "mac":       entry["mac"],
                "neighbors": entry["neighbors"],
                "hop":       entry["hop"],
                "id":        entry["id"]
            }
            for name, entry in PEER_DICT.items()
        }
    }
    with open(PEER_FILE, "w") as f:
        json.dump(data, f)
    print(f"[PEERS] Saved {len(PEER_DICT)} peers.")


def load_peers():
    """
    Load PEER_DICT from peer_file.json.
    Re-registers all direct neighbors with the ESP-NOW driver.
    """
    global PEER_DICT
    try:
        with open(PEER_FILE, "r") as f:
            data = json.load(f)
    except (OSError, ValueError):
        print("[PEERS] No peer file found or file corrupted, starting fresh.")
        PEER_DICT = {}
        return

    PEER_DICT = data.get("peers", {})

    # Re-register direct neighbors with ESP-NOW driver
    for name in _get_my_neighbors():
        if name in PEER_DICT:
            _espnow_add_peer_safe(mac_bytes(PEER_DICT[name]["mac"]))

    print(f"[PEERS] Loaded {len(PEER_DICT)} peers.")


# ── Internal Helpers ──────────────────────────────────────────────────────────

def _get_my_neighbors() -> list:
    """Return list of peer names that are direct neighbors of this node."""
    return [name for name, entry in PEER_DICT.items()
            if LOCAL_NAME in entry.get("neighbors", [])]


def _espnow_add_peer_safe(mac: bytes):
    """Add a peer to ESP-NOW, silently ignoring duplicate registration errors."""
    try:
        get_espnow().add_peer(mac)
    except OSError:
        pass


def mac_bytes(mac_str: str) -> bytes:
    """Convert 'AA:BB:CC:DD:EE:FF' to bytes."""
    return bytes(int(x, 16) for x in mac_str.split(':'))


def format_mac(mac: bytes) -> str:
    """Convert bytes to 'AA:BB:CC:DD:EE:FF'."""
    return ':'.join(f'{b:02X}' for b in mac)


def _name_for_mac(mac: bytes):
    """Reverse-lookup a peer name from MAC bytes. Returns None if unknown."""
    mac_str = format_mac(mac)
    for name, entry in PEER_DICT.items():
        if entry["mac"].upper() == mac_str.upper():
            return name
    return None


def _get_local_id() -> int:
    """Return this node's provisioned 1-byte ID."""
    if LOCAL_ID is None:
        raise RuntimeError("Node ID not set. Check config.json.")
    return LOCAL_ID


# [PATCH] Sync-loop prevention utility
def peer_dict_hash() -> int:
    """
    Return a simple DJB2 hash of the current PEER_DICT contents.
    Used by handle_sync_packet() to detect whether an incoming sync
    actually contains new information.
    """
    raw = json.dumps(PEER_DICT, sort_keys=True)
    h = 5381
    for ch in raw:
        h = ((h << 5) + h + ord(ch)) & 0xFFFFFFFF
    return h


# ── Peer Management ──────────────────────────────────────────────────────────

def add_peer(name: str, mac_str: str, neighbors: list, hop: int, node_id: int):
    """
    Add or update a peer in the local network map.
    If the peer is a direct neighbor, also registers it with the ESP-NOW driver.
    """
    PEER_DICT[name] = {
        "mac":       mac_str.upper(),
        "neighbors": neighbors,
        "hop":       hop,
        "id":        node_id
    }
    if name in _get_my_neighbors():
        _espnow_add_peer_safe(mac_bytes(mac_str))
        print(f"[PEERS] '{name}' added as direct neighbor (hop {hop}, ID {node_id}).")
    else:
        print(f"[PEERS] '{name}' added to map (hop {hop}, ID {node_id}, not a direct neighbor).")
    save_peers()


def remove_peer(name: str):
    """Remove a peer from the local map and clean up neighbor references."""
    if name not in PEER_DICT:
        print(f"[PEERS] Unknown peer '{name}'.")
        return
    PEER_DICT.pop(name)
    for entry in PEER_DICT.values():
        if name in entry["neighbors"]:
            entry["neighbors"].remove(name)
    save_peers()
    print(f"[PEERS] '{name}' removed.")


def list_peers():
    """Print all known peers with their hop count and neighbor status."""
    if not PEER_DICT:
        print("[PEERS] No peers known.")
        return
    my_neighbors = _get_my_neighbors()
    print(f"[PEERS] Known peers ({len(PEER_DICT)}):")
    for name, entry in PEER_DICT.items():
        tag = " <-- neighbor" if name in my_neighbors else ""
        print(f"  ID:{entry['id']:3d}  hop:{entry['hop']}  {name:20s}  {entry['mac']}{tag}")


# ── Peer List Sync (Mesh Propagation) ────────────────────────────────────────

def sync_peers_outward(exclude_name: str = None):
    """
    [PATCHED] Forward the full peer map to ALL direct neighbors.

    Previously only forwarded downstream. Now sends to every direct
    neighbor so newly added upstream-adjacent nodes also get the map.

    Args:
        exclude_name: optional peer name to skip (the node that just
                      sent us this sync, to avoid ping-pong).
    """
    global _last_sync_hash

    my_neighbors = _get_my_neighbors()
    payload = _build_sync_packet()

    # Update our own hash so we don't re-process our own broadcast
    _last_sync_hash = peer_dict_hash()

    sent_count = 0
    for name in my_neighbors:
        if name == exclude_name:
            continue
        if name not in PEER_DICT:
            continue
        entry = PEER_DICT[name]
        target_mac = mac_bytes(entry["mac"])
        espnow_send(target_mac, payload)
        print(f"[SYNC] Forwarded peer list to '{name}' (hop {entry['hop']}).")
        sent_count += 1

    print(f"[SYNC] Sync complete -- sent to {sent_count} neighbor(s).")


def _build_sync_packet() -> bytes:
    """
    Pack the full peer map into a sync payload.
    Format: ACT_SYNC_PEERS (1B) + JSON-encoded peer dict.
    """
    body   = json.dumps({"peers": PEER_DICT})
    packet = bytes([ACT_SYNC_PEERS]) + body.encode()
    if len(packet) > 250:
        print(f"[SYNC] WARNING: sync packet is {len(packet)}B, exceeds 250B ESP-NOW limit!")
    return packet


def handle_sync_packet(payload: bytes, sender_mac: bytes = None):
    """
    [PATCHED] Process an inbound ACT_SYNC_PEERS packet.

    1. Deserialize inbound peer map.
    2. Compare against _last_sync_hash to detect duplicates.
    3. Merge received peers, never overwriting our own entry.
    4. Re-register any new direct neighbors with ESP-NOW.
    5. Save, update hash, and forward outward (excluding sender).
    """
    global PEER_DICT, _last_sync_hash

    try:
        data = json.loads(payload[1:].decode())
    except Exception as e:
        print(f"[SYNC] Bad sync packet: {e}")
        return

    incoming_peers = data.get("peers", {})

    # ── Merge incoming peers into local map ──────────────────────
    changed = False
    for name, entry in incoming_peers.items():
        if name == LOCAL_NAME:
            continue  # never overwrite our own entry
        if PEER_DICT.get(name) != entry:
            PEER_DICT[name] = entry
            changed = True

    if not changed:
        print("[SYNC] Peer map already up to date.")
        return

    # ── Hash check to prevent infinite rebroadcast ───────────────
    new_hash = peer_dict_hash()
    if new_hash == _last_sync_hash:
        print("[SYNC] Hash unchanged after merge -- suppressing rebroadcast.")
        return

    # ── Re-register any new direct neighbors with ESP-NOW ────────
    for name in _get_my_neighbors():
        if name in PEER_DICT:
            _espnow_add_peer_safe(mac_bytes(PEER_DICT[name]["mac"]))

    save_peers()
    _last_sync_hash = new_hash

    # ── Forward outward, excluding the sender ────────────────────
    exclude = _name_for_mac(sender_mac) if sender_mac else None
    print(f"[SYNC] Peer map updated, forwarding outward (excluding '{exclude}').")
    sync_peers_outward(exclude_name=exclude)


# ── Packet Builder ────────────────────────────────────────────────────────────

def create_msg_packet(
    dest_mac: bytes,
    action: int,
    message: bytes = b'',
    health: dict = None,
    trail: list = None
) -> bytes:
    """
    Build a full 67-byte packet.

    Layout:
        Bytes  0-5  : Destination MAC     (6B)
        Bytes  6-11 : Sender MAC          (6B)
        Byte   12   : Action byte         (1B)
        Byte   13   : Message length      (1B)
        Bytes 14-45 : Message payload     (32B, zero-padded)
        Byte   46   : Flags               (1B)
        Bytes 47-56 : Health report       (10B, zeroed if absent)
        Bytes 57-66 : Hop trail           (10B, 0x00 = empty slot)
    """
    pkt = bytearray(PKT_TOTAL_SIZE)

    # Destination MAC (bytes 0-5)
    pkt[PKT_DEST_START:PKT_DEST_END] = dest_mac

    # Sender MAC (bytes 6-11)
    pkt[PKT_SENDER_START:PKT_SENDER_END] = mac_local

    # Action byte (byte 12)
    pkt[PKT_ACTION] = action

    # Message length + payload (bytes 13-45)
    if len(message) > MAX_MSG_BYTES:
        print(f"[PKT] Warning: message truncated to {MAX_MSG_BYTES} bytes.")
        message = message[:MAX_MSG_BYTES]
    pkt[PKT_MSG_LEN] = len(message)
    pkt[PKT_MSG_START:PKT_MSG_START + len(message)] = message

    # Flags byte (byte 46)
    flags = 0x00
    if health is not None:
        flags |= FLAG_HEALTH
    pkt[PKT_FLAGS] = flags

    # Health block (bytes 47-56, optional)
    if health is not None:
        pkt[PKT_HEALTH_START:PKT_HEALTH_END] = _encode_health(health)

    # Hop trail (bytes 57-66)
    pkt[PKT_TRAIL_START:PKT_TRAIL_END] = _encode_trail(trail)

    return bytes(pkt)


# ── Health Encode / Decode ────────────────────────────────────────────────────

def _encode_health(health: dict) -> bytes:
    """
    Pack a health dict into exactly 10 bytes.
        Byte 0      : temp (signed, -128..127)
        Byte 1      : battery %  (0..100)
        Bytes 2-5   : uptime seconds (uint32)
        Bytes 6-9   : reserved (zeroed)
    """
    temp    = max(-128, min(127, health.get("temp", 0)))
    battery = max(0,    min(100, health.get("battery", 0)))
    uptime  = health.get("uptime", 0) & 0xFFFFFFFF
    return struct.pack(">bBIxxxx", temp, battery, uptime)


def decode_health(pkt: bytes) -> dict:
    """Unpack the health block from a received packet into a dict."""
    temp, battery, uptime = struct.unpack(">bBI", pkt[PKT_HEALTH_START:PKT_HEALTH_START + 6])
    return {"temp": temp, "battery": battery, "uptime": uptime}


# ── Trail Encode / Decode ─────────────────────────────────────────────────────

def _encode_trail(trail: list) -> bytes:
    """
    Pack the hop trail into exactly MAX_TRAIL_HOPS (10) bytes.
    Appends this node's own ID, then zero-pads.
    """
    trail = list(trail) if trail else []

    local_id = _get_local_id()
    if local_id in trail:
        print(f"[PKT] WARNING: Loop detected -- node ID {local_id} already in trail: {trail}")

    trail.append(local_id)

    if len(trail) > MAX_TRAIL_HOPS:
        print(f"[PKT] WARNING: Trail full ({MAX_TRAIL_HOPS} hops), packet may be looping.")
        trail = trail[:MAX_TRAIL_HOPS]

    trail_bytes = bytearray(MAX_TRAIL_HOPS)
    for i, node_id in enumerate(trail):
        trail_bytes[i] = node_id

    return bytes(trail_bytes)


def decode_trail(pkt: bytes) -> list:
    """Extract the hop trail. Stops at first 0x00."""
    trail = []
    for b in pkt[PKT_TRAIL_START:PKT_TRAIL_END]:
        if b == 0x00:
            break
        trail.append(b)
    return trail


# ── Packet Parser ─────────────────────────────────────────────────────────────

def parse_packet(pkt: bytes) -> dict:
    """Decode a raw 67-byte packet into a readable dict."""
    if len(pkt) != PKT_TOTAL_SIZE:
        print(f"[PKT] Bad packet length: {len(pkt)}, expected {PKT_TOTAL_SIZE}")
        return {}

    flags      = pkt[PKT_FLAGS]
    msg_len    = pkt[PKT_MSG_LEN]
    has_health = bool(flags & FLAG_HEALTH)

    return {
        "dest":    format_mac(pkt[PKT_DEST_START:PKT_DEST_END]),
        "sender":  format_mac(pkt[PKT_SENDER_START:PKT_SENDER_END]),
        "action":  pkt[PKT_ACTION],
        "msg_len": msg_len,
        "message": pkt[PKT_MSG_START:PKT_MSG_START + msg_len],
        "flags":   flags,
        "health":  decode_health(pkt) if has_health else None,
        "trail":   decode_trail(pkt),
        "raw":     pkt,  # [PATCH] preserve raw bytes for forwarding
    }


# ── Send ──────────────────────────────────────────────────────────────────────

def espnow_send(peer_mac: bytes, packet: bytes):
    """Send a packet to a peer MAC. Peer must already be registered."""
    e = get_espnow()
    try:
        e.send(peer_mac, packet)
    except OSError as err:
        print(f"[ESP-NOW] Send failed to {format_mac(peer_mac)}: {err}")


# ── Receive Dispatcher ────────────────────────────────────────────────────────

def on_receive(e):
    """Receive callback. Called by ESP-NOW IRQ with the ESPNow object."""
    mac, raw = e.irecv(0)
    print("[RAW RX] From: %s  len: %d" % (format_mac(mac), len(raw) if raw else 0))  # ← add this
    if mac is None:
        return
    

    sender_name = _name_for_mac(mac)
    if sender_name is None:
        print(f"[WARN] Packet from unknown MAC {format_mac(mac)} -- rejected.")
        return

    if not raw:
        return

    # [PATCH] Route sync packets directly, passing sender MAC
    if raw[0] == ACT_SYNC_PEERS:
        handle_sync_packet(raw, sender_mac=mac)
        return

    pkt = parse_packet(raw)
    if not pkt:
        return

    action = pkt["action"]

    if action == ACT_TEST:
        print(f"[TEST] Ping from '{sender_name}'")

    elif action == ACT_SENSOR_RPT:
        print(f"[SENSOR] Report from '{sender_name}': {pkt['message']}")

    elif action == ACT_REPORT_HOME:
        handle_report_home(pkt)

    elif action == ACT_REQ_ACTION:
        print(f"[ACTION] Request from '{sender_name}': {pkt['message']}")
        global REQUEST_FLAG
        REQUEST_FLAG = True  # Set a global flag that the main loop can check

    elif action == ACT_RPT_ACTION:
        print(f"[ACTION] Report from '{sender_name}': {pkt['message']}")

    else:
        print(f"[RX] Unknown action 0x{action:02X} from '{sender_name}'")


# ── Return-to-Home Routing ────────────────────────────────────────────────────

def _find_next_hop_toward_home():
    """
    Find the best neighbor to forward toward home (hop 0).
    Returns neighbor MAC as bytes, or None.
    """
    my_neighbors = _get_my_neighbors()
    best_name = None
    best_hop  = LOCAL_HOP

    for name in my_neighbors:
        if name not in PEER_DICT:
            continue
        peer_hop = PEER_DICT[name]["hop"]
        if peer_hop < best_hop:
            best_hop  = peer_hop
            best_name = name

    if best_name is None:
        print("[ROUTE] No neighbor closer to home found. Are we home?")
        return None

    print(f"[ROUTE] Next hop toward home: '{best_name}' (hop {best_hop})")
    return mac_bytes(PEER_DICT[best_name]["mac"])


def handle_report_home(pkt: dict):
    """
    Handle ACT_REPORT_HOME.
    If home: serialize to UART for the PC GUI.
    If not home: forward toward home.
    """
    sender  = pkt.get("sender", "unknown")
    message = pkt.get("message", b"")
    trail   = pkt.get("trail", [])
    raw     = pkt.get("raw", b'\x00' * PKT_TOTAL_SIZE)

    if LOCAL_HOP == 0:
        health = decode_health(raw) if pkt.get("flags", 0) & FLAG_HEALTH else {}
        try:
            msg_str = message.decode("utf-8").rstrip("\x00")
        except UnicodeError:
            msg_str = ''.join('%02x' % b for b in message)
        output = {
            "type":      "sensor_report",
            "sender":    sender,
            "message":   msg_str,
            "trail":     trail,
            "health":    health,
            "timestamp": None
        }
        print(json.dumps(output))
        return

    next_hop_mac = _find_next_hop_toward_home()
    if next_hop_mac is None:
        print(f"[ROUTE] Dead end! Cannot forward from '{sender}'.")
        return

    print(f"[ROUTE] Forwarding ACT_REPORT_HOME from '{sender}' toward home.")
    forward_packet(pkt, next_hop_mac)


# ── Packet Forwarding ─────────────────────────────────────────────────────────

def forward_packet(pkt: dict, next_hop_mac: bytes):
    """
    Forward a parsed packet to the next hop.
    Preserves original dest and message. Drops health on forward.
    """
    new_pkt = create_msg_packet(
        dest_mac = mac_bytes(pkt["dest"]),
        action   = pkt["action"],
        message  = pkt["message"],
        health   = None,
        trail    = pkt["trail"]
    )
    espnow_send(next_hop_mac, new_pkt)


# ── UART Serial Interface (Host ESP Only) ────────────────────────────────────

def handle_serial_command(line: str):
    """
    Parse and execute a command from the Host PC over UART.

    Commands:
        ADD <name> <mac> <hop> <id> <neighbor1,neighbor2,...>
        REMOVE <name>
        LIST
        SYNC
        SETNAME <name>
        SETHOP <hop>
        SETID <id>
    """
    global LOCAL_NAME, LOCAL_HOP, LOCAL_ID

    parts = line.strip().split()
    if not parts:
        return
    cmd = parts[0].upper()

    if cmd == "ADD" and len(parts) >= 5:
        name      = parts[1]
        mac_str   = parts[2]
        hop       = int(parts[3])
        node_id   = int(parts[4])
        neighbors = parts[5].split(',') if len(parts) > 5 else []
        add_peer(name, mac_str, neighbors, hop, node_id)
        sync_peers_outward()

    elif cmd == "REMOVE" and len(parts) == 2:
        remove_peer(parts[1])
        sync_peers_outward()

    elif cmd == "LIST":
        list_peers()

    elif cmd == "SYNC":
        # [PATCH] Explicit serial trigger for full mesh sync
        print("[UART] SYNC requested -- pushing peer map to all neighbors.")
        sync_peers_outward()

    elif cmd == "SETNAME" and len(parts) == 2:
        LOCAL_NAME = parts[1]
        save_config()

    elif cmd == "SETHOP" and len(parts) == 2:
        LOCAL_HOP = int(parts[1])
        save_config()

    elif cmd == "SETID" and len(parts) == 2:
        LOCAL_ID = int(parts[1])
        save_config()

    else:
        print(f"[UART] Unknown command: {line.strip()}")


def poll_serial():
    """
    Non-blocking UART poll. Call every main loop iteration on the Host ESP.
    """
    import select
    if select.select([sys.stdin], [], [], 0)[0]:  # ← was missing [0]:
        line = sys.stdin.readline()
        if line:
            handle_serial_command(line)


# ── Boot Sequence ─────────────────────────────────────────────────────────────

def boot():
    """
    Full boot sequence. Call once from main.py.
    Order matters -- ESP-NOW must be up before peers are loaded.
    """
    espnow_setup()                          # 1. hardware up
    load_config()                           # 2. identity
    load_peers()                            # 3. network map + re-register neighbors
    espnow_set_recv_callback(on_receive)    # 4. start listening
