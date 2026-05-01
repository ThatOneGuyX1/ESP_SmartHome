from common_esp import *
import time
import json

espnow_setup()
espnow_set_recv_callback()

led_booting()

last_hello = 0
last_route_adv = 0
last_ping = 0

host_cost = 999

led_searching()

# =======================
# HELLO
# =======================
def send_hello():

    packet = create_msg_packet(
        dest=BROADCAST_MAC,
        send=get_local_mac(),
        message="HELLO",
        health={"bat":95},
        act=ACT_HELLO
    )

    espnow_send(BROADCAST_MAC, packet)

# =======================
# ROUTE ADVERTISEMENT
# =======================
def send_route_adv():

    payload = json.dumps({
        "cost": host_cost
    })

    packet = create_msg_packet(
        dest=BROADCAST_MAC,
        send=get_local_mac(),
        message=payload,
        health={"bat":95},
        act=ACT_ROUTE
    )

    espnow_send(BROADCAST_MAC, packet)

# =======================
# BEST ROUTE
# =======================
def choose_best_route():

    return get_route(HOST_MAC)

# =======================
# SEND PING
# =======================
def send_ping():

    route = choose_best_route()

    if not route:

        led_searching()

        print("[NO ROUTE]")

        return

    next_hop = route["next_hop"]

    packet = create_msg_packet(
        dest=HOST_MAC,
        send=get_local_mac(),
        message="PING",
        health={"bat":95},
        path=[get_local_mac()],
        ttl=6,
        act=ACT_PING
    )

    espnow_send(next_hop, packet)

    if next_hop == HOST_MAC:
        led_direct_host()
    else:
        led_relay_route()

# =======================
# FORWARD
# =======================
def forward_packet(data, next_hop):

    if data["ttl"] <= 1:
        return

    packet_id=data["packet_id"]

    led_forwarding()

    print(f"""
[FORWARD]

TO:
{format_mac(next_hop)}
""")

    packet = create_msg_packet(
        dest=data["destination"],
        send=data["sender"],
        message=data["message"],
        health={"bat":data["battery"]},
        path=data["path"] + [get_local_mac()],
        ttl=data["ttl"] - 1,
        act=data["action"]
    )

    espnow_send(next_hop, packet)

    time.sleep_ms(120)

# =======================
# PROCESS
# =======================
def process_packet(mac, msg):

    global host_cost

    data = parse_msg_packet(msg)

    if not data:
        return

    if packet_seen(
        data["sender"],
        data["packet_id"]
    ):
        return

    sender = data["sender"]

    espnow_add_peer(sender)

    e = get_espnow()

    peer_info = e.peers_table.get(sender)

    rssi = peer_info[0] if peer_info else -100

    # =======================
    # DIRECT HOST
    # =======================
    if sender == HOST_MAC:

        # =======================
        # DIRECT ROUTE PENALTY
        # =======================
        DIRECT_HOST_PENALTY = 10

        direct_cost = 1 + DIRECT_HOST_PENALTY

        current = get_route(HOST_MAC)

        update = False

        if current is None:
            update = True

        elif direct_cost < current["cost"]:
            update = True

        if update:

            update_route(
                HOST_MAC,
                HOST_MAC,
                direct_cost
            )

            host_cost = direct_cost

            print(f"""
[DIRECT HOST ROUTE]

PENALIZED COST:
{direct_cost}
""")

    # =======================
    # ROUTE ADV
    # =======================
    elif data["action"] == ACT_ROUTE:

        try:

            payload = json.loads(data["message"])

            advertised_cost = payload["cost"]

            # RSSI penalty
            link_cost = abs(rssi) // 8

            total_cost = advertised_cost + link_cost + 1

            current = get_route(HOST_MAC)

            update = False

            if current is None:
                update = True

            elif total_cost < current["cost"]:
                update = True

            if update:

                update_route(
                    HOST_MAC,
                    sender,
                    total_cost
                )

                host_cost = total_cost

                print(f"""
[ROUTE UPDATE]

NEXT HOP:
{format_mac(sender)}

COST:
{total_cost}
""")

        except Exception as e:

            print("[ROUTE ERROR]", e)

    # =======================
    # FORWARDING
    # =======================
    if data["action"] in [ACT_PING, ACT_ROUTE]:       

        route = choose_best_route()

        if route:

            next_hop = route["next_hop"]

            if next_hop != mac:

                forward_packet(
                    data,
                    next_hop
                )

# =======================
# MAIN LOOP
# =======================
while True:

    pkt = get_next_packet()

    if pkt:

        mac, msg = pkt[:2]

        if msg:
            process_packet(mac, msg)

    cleanup_routes()
    cleanup_seen_packets()

    now = time.ticks_ms()

    if time.ticks_diff(now, last_hello) > 2000:

        send_hello()

        last_hello = now

    if time.ticks_diff(now, last_route_adv) > 4000:

        send_route_adv()

        last_route_adv = now

    if time.ticks_diff(now, last_ping) > 5000:

        send_ping()

        last_ping = now

    time.sleep_ms(50)