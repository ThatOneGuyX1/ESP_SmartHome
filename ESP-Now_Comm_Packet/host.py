from common_esp import *
import time

# =========================
# SETUP
# =========================
espnow_setup()
espnow_set_recv_callback()

print("HOST:", format_mac(get_local_mac()))

NETWORK_MAP = {}

# =========================
# PROCESS PACKETS
# =========================
def process_packet(mac, msg):

    data = parse_msg_packet(msg)

    if not data:
        return

    sender = data["sender"]

    espnow_add_peer(sender)

    e = get_espnow()

    peer_info = e.peers_table.get(mac)

    rssi = peer_info[0] if peer_info else -100

    NETWORK_MAP[format_mac(sender)] = {
        "rssi": rssi,
        "battery": data["battery"],
        "last_seen": time.ticks_ms(),
        "path": [format_mac(p) for p in data["path"]]
    }

    # Send route advertisement
    packet = create_msg_packet(
        dest=BROADCAST_MAC,
        send=get_local_mac(),
        message='{"cost":0}',
        health={"bat": 100},
        act=ACT_ROUTE
    )

    espnow_send(BROADCAST_MAC, packet)

# =========================
# ASCII NETWORK DISPLAY
# =========================
def signal_bars(rssi):

    if rssi > -55:
        return "█████"

    elif rssi > -65:
        return "████"

    elif rssi > -75:
        return "███"

    elif rssi > -85:
        return "██"

    return "█"

def display_network():

    print("\033[2J\033[H")

    print("=" * 60)
    print("SELF-HEALING ESP-NOW MESH")
    print("=" * 60)

    print("\n                 [ HOST ]\n")

    now = time.ticks_ms()

    for node, info in list(NETWORK_MAP.items()):

        age = time.ticks_diff(
            now,
            info["last_seen"]
        )

        if age > 15000:

            del NETWORK_MAP[node]
            continue

        print(f"""
        ├── {node[-5:]}
        │     RSSI : {info['rssi']}
        │     LINK : {signal_bars(info['rssi'])}
        │     BAT  : {info['battery']}%
        │     PATH : {' -> '.join(info['path'])}
        """)

    print("=" * 60)

# =========================
# MAIN LOOP
# =========================
last_display = 0

while True:

    pkt = get_next_packet()

    if pkt:

        mac, msg = pkt[:2]

        if msg:
            process_packet(mac, msg)

    if time.ticks_diff(
        time.ticks_ms(),
        last_display
    ) > 2000:

        display_network()

        last_display = time.ticks_ms()

    time.sleep_ms(50)