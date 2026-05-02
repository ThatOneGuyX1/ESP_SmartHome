from common_esp import *
import time
import json

# =========================
# SETUP
# =========================

FORWARD_SEEN = {}
FORWARD_TIMEOUT = 5000

last_forward_event = 0
FORWARD_FLASH_MS = 150

espnow_setup()
espnow_set_recv_callback()

print("NODE B:", format_mac(get_local_mac()))

espnow_add_peer(HOST_MAC)

led_booting()

last_hello = 0
last_route_adv = 0
last_host_seen = 0

host_cost = 1

ROUTE_TIMEOUT = 10000


# =========================
# FORWARD DEDUP KEY
# =========================

def forward_key(data):
    return (data["packet_id"], data["sender"])


def forward_seen(key):
    now = time.ticks_ms()

    if key in FORWARD_SEEN:
        return True

    FORWARD_SEEN[key] = now
    return False


def cleanup_forward_seen():
    now = time.ticks_ms()

    remove = []

    for key, ts in FORWARD_SEEN.items():
        if time.ticks_diff(now, ts) > FORWARD_TIMEOUT:
            remove.append(key)

    for key in remove:
        del FORWARD_SEEN[key]


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
# FORWARD PACKET (FIXED)
# =========================

def forward_packet(data):

    global last_host_seen, last_forward_event

    if data["ttl"] <= 1:
        return

    # prevent loops via path history
    if get_local_mac() in data["path"]:
        return

    print(f"""
[FORWARDING]
FROM: {format_mac(data['sender'])}
TO HOST: {format_mac(HOST_MAC)}
""")

    new_packet = create_msg_packet(
        dest=data["destination"],
        send=data["sender"],
        message=data["message"],
        health={"bat": data["battery"]},
        path=data["path"] + [get_local_mac()],
        ttl=data["ttl"] - 1,
        act=data["action"]
    )

    espnow_send(HOST_MAC, new_packet)

    last_forward_event = time.ticks_ms()
    last_host_seen = time.ticks_ms()


# =========================
# PROCESS PACKETS
# =========================

def process_packet(mac, msg):

    global last_host_seen

    data = parse_msg_packet(msg)

    if not data:
        return

    # global duplicate suppression
    if packet_seen(data["sender"], data["packet_id"]):
        return

    sender = data["sender"]

    if sender != get_local_mac():
        espnow_add_peer(sender)

    # host heartbeat
    if sender == HOST_MAC:

        update_route(
            HOST_MAC,
            HOST_MAC,
            1
        )

        last_host_seen = time.ticks_ms()

        print("[NODE B] Direct host route")

    # =========================
    # RELAY FILTER (STRICT FIX)
    # =========================

    if (
        data["action"] == ACT_PING
        and data["destination"] == HOST_MAC
        and data["sender"] != get_local_mac()
        and get_local_mac() not in data["path"]
    ):

        key = forward_key(data)

        if forward_seen(key):
            return

        forward_packet(data)


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
    # LED STATE MACHINE
    # =========================

    age = time.ticks_diff(now, last_host_seen)
    flash_age = time.ticks_diff(now, last_forward_event)

    if flash_age < FORWARD_FLASH_MS:

        led_forwarding()

    elif age < ROUTE_TIMEOUT:

        led_direct_host()

    else:

        led_searching()

    # =========================
    # PERIODIC TASKS
    # =========================

    if time.ticks_diff(now, last_hello) > 2000:

        send_hello()
        last_hello = now

    if time.ticks_diff(now, last_route_adv) > 4000:

        send_route_advertisement()
        last_route_adv = now

    cleanup_seen_packets()
    cleanup_forward_seen()

    time.sleep_ms(50)