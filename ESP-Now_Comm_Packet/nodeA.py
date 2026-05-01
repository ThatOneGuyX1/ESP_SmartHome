from common_esp import *
import time
import json

# =========================
# SETUP
# =========================
espnow_setup()
espnow_set_recv_callback()

print("NODE A:", format_mac(get_local_mac()))

NODE_B_MAC = b'\x58\xE6\xC5\xF6\x79\xE0'

espnow_add_peer(NODE_B_MAC)
espnow_add_peer(HOST_MAC)

led_booting()

last_hello = 0
last_route_adv = 0
last_ping = 0
last_host_seen = 0

host_cost = 999

ROUTE_TIMEOUT = 10000

# =========================
# SEND HELLO
# =========================
def send_hello():

    packet = create_msg_packet(
        dest=BROADCAST_MAC,
        send=get_local_mac(),
        message="HELLO",
        health={"bat": 95},
        act=ACT_HELLO
    )

    espnow_send(BROADCAST_MAC, packet)

# =========================
# ROUTE ADVERTISEMENT
# =========================
def send_route_advertisement():

    payload = json.dumps({
        "cost": host_cost
    })

    packet = create_msg_packet(
        dest=BROADCAST_MAC,
        send=get_local_mac(),
        message=payload,
        health={"bat": 95},
        act=ACT_ROUTE
    )

    espnow_send(BROADCAST_MAC, packet)

# =========================
# SEND PING THROUGH RELAY
# =========================
def send_ping():

    packet = create_msg_packet(
        dest=HOST_MAC,
        send=get_local_mac(),
        message="PING FROM NODE A",
        health={"bat": 95},
        path=[get_local_mac()],
        ttl=5,
        act=ACT_PING
    )

    espnow_send(NODE_B_MAC, packet)

    print("[NODE A] Routed through Node B")

# =========================
# PROCESS PACKETS
# =========================
def process_packet(mac, msg):

    global host_cost
    global last_host_seen

    data = parse_msg_packet(msg)

    if not data:
        return

    if packet_seen(data["sender"], data["packet_id"]):
        return

    sender = data["sender"]

    espnow_add_peer(sender)

    # =========================
    # DIRECT HOST ROUTE
    # =========================
    # if sender == HOST_MAC:

    #     update_route(
    #         HOST_MAC,
    #         HOST_MAC,
    #         1
    #     )

    #     host_cost = 1
    #     last_host_seen = time.ticks_ms()

    #     print("[NODE A] Direct route to host")

    # =========================
    # RELAY ROUTE VIA NODE B
    # =========================
    elif sender == NODE_B_MAC and data["action"] == ACT_ROUTE:

        try:
            payload = json.loads(data["message"])

            relay_cost = payload.get("cost", 999)

            host_cost = relay_cost + 1

            update_route(
                HOST_MAC,
                NODE_B_MAC,
                host_cost
            )

            last_host_seen = time.ticks_ms()

            print("[NODE A] Relay route active via Node B")

        except:
            pass        

# =========================
# MAIN LOOP
# =========================
while True:

    now = time.ticks_ms()

    pkt = get_next_packet()

    if pkt:

        mac, msg = pkt[:2]

        if msg:
            process_packet(mac, msg)

    # =========================
    # ROUTE HEALTH
    # =========================
    age = time.ticks_diff(now, last_host_seen)

    if age < ROUTE_TIMEOUT:

        route = get_best_route(HOST_MAC)

        if route:

            if route["next_hop"] == HOST_MAC:
                led_direct_host()
            else:
                led_relay_route()

    else:

        host_cost = 999
        led_searching()

    if time.ticks_diff(now, last_hello) > 2000:

        send_hello()
        last_hello = now

    if time.ticks_diff(now, last_route_adv) > 4000:

        send_route_advertisement()
        last_route_adv = now

    if time.ticks_diff(now, last_ping) > 5000:

        send_ping()
        last_ping = now

    cleanup_seen_packets()

    time.sleep_ms(50)