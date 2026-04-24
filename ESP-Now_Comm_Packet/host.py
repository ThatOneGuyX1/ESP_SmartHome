from common_esp import *
import time

# =========================
# SETUP
# =========================
espnow_setup()
espnow_set_recv_callback()

print("HOST MAC:", format_mac(get_local_mac()))

NETWORK_MAP = {}
KNOWN_PEERS = set()

# =========================
# TIMERS
# =========================
last_display = 0
last_rssi_update = 0

# =========================
# PROCESS PACKETS
# =========================
def process_packet(mac, msg):

    data = parse_msg_packet(msg)

    if not data:
        return

    sender_mac = data["sender"]

    # -------------------------
    # ADD NEW PEERS
    # -------------------------
    if sender_mac not in KNOWN_PEERS:

        espnow_add_peer(sender_mac)
        KNOWN_PEERS.add(sender_mac)

        print(f"[NEW PEER] {format_mac(sender_mac)}")

    # -------------------------
    # GET RSSI
    # -------------------------
    e = get_espnow()

    peer_info = e.peers_table.get(sender_mac, None)

    rssi = peer_info[0] if peer_info else None

    # -------------------------
    # LATENCY
    # -------------------------
    now = time.ticks_ms()

    latency = time.ticks_diff(
        now,
        data["timestamp"]
    )

    # -------------------------
    # UPDATE NETWORK MAP
    # -------------------------
    NETWORK_MAP[format_mac(sender_mac)] = {
        "last_seen": now,
        "battery": data["battery"],
        "rssi": rssi,
        "latency": latency,
        "path": [format_mac(p) for p in data["path"]]
    }

# =========================
# DISPLAY NETWORK
# =========================
def display_network():

    print("\n" + "=" * 50)
    print("NETWORK MAP")
    print("=" * 50)

    now = time.ticks_ms()

    for node, info in list(NETWORK_MAP.items()):

        age = time.ticks_diff(
            now,
            info["last_seen"]
        )

        # Remove dead nodes
        if age > 15000:

            print(f"[TIMEOUT] Removing {node}")

            del NETWORK_MAP[node]
            continue

        print(f"""
Node: {node}
  RSSI: {info['rssi']}
  Latency: {info['latency']} ms
  Battery: {info['battery']}%
  Path: {' -> '.join(info['path'])}
  Last Seen: {age} ms ago
""")

    print("=" * 50)

# =========================
# FIND STRONGEST NODE
# =========================
def find_strongest_node():

    best_node = None
    best_rssi = -999

    for mac_str, info in NETWORK_MAP.items():

        rssi = info["rssi"]

        if rssi is None:
            continue

        if rssi > best_rssi:

            best_rssi = rssi
            best_node = mac_str

    return best_node, best_rssi

# =========================
# BROADCAST STRONGEST NODE
# =========================
def broadcast_strongest_node():

    best_node, best_rssi = find_strongest_node()

    if not best_node:
        return

    best_mac = bytes(
        int(x, 16)
        for x in best_node.split(':')
    )

    packet = create_msg_packet(
        dest=best_mac,
        send=get_local_mac(),
        message="STRONGEST",
        health={"bat": 100},
        act=0xD1
    )

    # Broadcast to ALL nodes
    espnow_send(
        b'\xff\xff\xff\xff\xff\xff',
        packet
    )

    print(f"""
[HOST]
Strongest Node:
  {best_node}
  RSSI = {best_rssi}
""")

# =========================
# MAIN LOOP
# =========================
while True:
    # -------------------------
    # RECEIVE PACKETS
    # -------------------------
    pkt = get_next_packet()

    if pkt:
        mac, msg = pkt[:2]

        if msg:
            process_packet(mac, msg)

    # -------------------------
    # DISPLAY NETWORK
    # -------------------------
    if time.ticks_diff(
        time.ticks_ms(),
        last_display
    ) > 2000:

        display_network()

        last_display = time.ticks_ms()

    # -------------------------
    # UPDATE STRONGEST NODE
    # EVERY 5 SECONDS
    # -------------------------
    if time.ticks_diff(
        time.ticks_ms(),
        last_rssi_update
    ) > 5000:

        broadcast_strongest_node()

        last_rssi_update = time.ticks_ms()