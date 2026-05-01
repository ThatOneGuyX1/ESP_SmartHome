from common_esp import *
import time
import json

# =========================
# SETUP
# =========================
last_forward_flash = 0
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
# FORWARD PACKET
# =========================
def forward_packet(data):

    global last_host_seen, last_forward_flash

    if data["ttl"] <= 1:

        print("[NODE B] TTL expired")
        return

    if get_local_mac() in data["path"]:
        return

    # led_forwarding()

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

    # time.sleep_ms(150)

    last_forward_flash = time.ticks_ms()
    last_host_seen = time.ticks_ms()

# =========================
# PROCESS PACKETS
# =========================
def process_packet(mac, msg):

    global last_host_seen

    data = parse_msg_packet(msg)

    if not data:
        return

    if packet_seen(data["sender"], data["packet_id"]):
        return

    sender = data["sender"]

    espnow_add_peer(sender)

    if sender == HOST_MAC:

        update_route(
            HOST_MAC,
            HOST_MAC,
            1
        )

        last_host_seen = time.ticks_ms()

        print("[NODE B] Direct host route")

    if (
        data["destination"] == HOST_MAC
        and data["sender"] != get_local_mac()
        and data["action"] == ACT_PING
    ):

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

    age = time.ticks_diff(now, last_host_seen)


    flash_age = time.ticks_diff(now, last_forward_flash)

    if flash_age < FORWARD_FLASH_MS:
        led_forwarding()

    elif age < ROUTE_TIMEOUT:
        led_direct_host()

    else:
        led_searching()

    if time.ticks_diff(now, last_hello) > 2000:

        send_hello()
        last_hello = now

    if time.ticks_diff(now, last_route_adv) > 4000:

        send_route_advertisement()
        last_route_adv = now

    cleanup_seen_packets()

    time.sleep_ms(50)