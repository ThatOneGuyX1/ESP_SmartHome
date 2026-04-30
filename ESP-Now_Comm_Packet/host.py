from common_esp import *
import time

espnow_setup()
espnow_set_recv_callback()

print("HOST MAC:", format_mac(get_local_mac()))

NETWORK_MAP = {}
KNOWN_PEERS = set()   # TRACK KNOWN PEERS

def process_packet(mac, msg, rssi):
    data = parse_msg_packet(msg)
    if not data:
        return

    sender = data["sender"]
    sender_mac_bytes = bytes.fromhex(sender.replace(':',''))

    # Only add peer ONCE
    if sender_mac_bytes not in KNOWN_PEERS:
        espnow_add_peer(sender_mac_bytes)
        KNOWN_PEERS.add(sender_mac_bytes)

    # Get RSSI from peers_table
    e = get_espnow()
    peer_info = e.peers_table.get(sender_mac_bytes, None)

    if peer_info:
        rssi = peer_info[0]
    else:
        rssi = None

    # Compute latency
    now = time.ticks_ms()
    latency = time.ticks_diff(now, data["timestamp"])

    # Update network map
    NETWORK_MAP[sender] = {
        "last_seen": now,
        "battery": data["battery"],
        "rssi": rssi,
        "latency": latency
    }

    # Send reply (keeps connection alive)
    reply_packet = create_msg_packet(
        dest=sender_mac_bytes,
        send=get_local_mac(),
        message="ack",
        health={"bat": 100},
        act=0x03
    )

    espnow_send(sender_mac_bytes, reply_packet)


def display_network():
    print("\n" + "="*50)
    print("NETWORK MAP")
    print("="*50)

    now = time.ticks_ms()

    for node, info in list(NETWORK_MAP.items()):
        age = time.ticks_diff(now, info["last_seen"])

        # Remove dead nodes (>15 sec)
        if age > 15000:
            del NETWORK_MAP[node]
            continue

        # Signal quality label
        if info["rssi"] is None:
            signal = "UNKNOWN"
        elif info["rssi"] > -50:
            signal = "STRONG"
        elif info["rssi"] > -70:
            signal = "MEDIUM"
        else:
            signal = "WEAK"

        print(f"""
Node: {node}
  RSSI: {info['rssi']} ({signal})
  Latency: {info['latency']} ms
  Battery: {info['battery']}%
  Last Seen: {age} ms ago
""")

    print("="*50)


# Main loop
last_display = 0

while True:
    pkt = get_next_packet()

    if pkt:
        if len(pkt) == 3:
            mac, msg, rssi = pkt
        else:
            mac, msg = pkt
            rssi = None

        if msg:
            process_packet(mac, msg, rssi)

    # refresh display every 2 seconds
    if time.ticks_diff(time.ticks_ms(), last_display) > 2000:
        display_network()
        last_display = time.ticks_ms()